"""
management command: seed_data

Reads rates_seed.parquet (Snappy-compressed) and upserts records into the
Rate table in chunks.  Running this command multiple times is safe — records
are inserted with ON CONFLICT (provider_name, rate_type, effective_date) DO UPDATE,
so re-runs are fully idempotent.

Real seed file columns (discovered from the actual file):
    provider         -> mapped to provider_name
    rate_type        -> used as-is
    rate_value       -> used as-is
    effective_date   -> used as-is
    ingestion_ts     -> stored in raw_payload only
    source_url       -> stored in raw_payload
    raw_response_id  -> stored in raw_payload
    currency         -> stored in raw_payload

Column aliases are defined in COLUMN_ALIASES on the Command class.
Add new mappings there if the upstream schema changes again.

Bad rows (null rate_value, unparseable date, missing provider, etc.) are logged
as WARNING and skipped — they never crash the worker.  The full raw row is
stored in raw_payload so failed rows can be replayed once fixed upstream.

Usage:
    python manage.py seed_data
    python manage.py seed_data --file /path/to/custom.parquet
    python manage.py seed_data --chunk-size 5000
    python manage.py seed_data --skip-if-exists
"""

import logging
import time
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from rates.models import Rate

logger = logging.getLogger("rates")

DEFAULT_PARQUET = Path(settings.BASE_DIR) / "data" / "rates_seed.parquet"
CHUNK_SIZE = 10_000


class Command(BaseCommand):
    help = "Seed the database from rates_seed.parquet (idempotent upsert)"

    # Maps every known column-name variant -> our canonical field name.
    # The real seed file uses "provider" not "provider_name".
    # Add new aliases here if the upstream schema changes again.
    COLUMN_ALIASES: dict = {
        "provider":        "provider_name",
        "ingestion_ts":    "ingestion_timestamp_src",  # don't clash with our own field
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=Path,
            default=DEFAULT_PARQUET,
            help="Path to the Parquet seed file",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=CHUNK_SIZE,
            help="Rows per DB batch (default 10 000)",
        )
        parser.add_argument(
            "--skip-if-exists",
            action="store_true",
            help="No-op if the Rate table already contains rows",
        )

    def handle(self, *args, **options):
        parquet_path: Path = options["file"]
        chunk_size: int = options["chunk_size"]
        skip_if_exists: bool = options["skip_if_exists"]

        if skip_if_exists and Rate.objects.exists():
            logger.info("seed_data: table non-empty and --skip-if-exists set; skipping.")
            self.stdout.write(self.style.WARNING("Skipped: data already present."))
            return

        if not parquet_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {parquet_path}"))
            raise SystemExit(1)

        logger.info(
            "seed_data started",
            extra={"file": str(parquet_path), "chunk_size": chunk_size},
        )
        t_start = time.monotonic()
        total_ok = 0
        total_bad = 0

        df = pd.read_parquet(parquet_path, engine="pyarrow")

        # Log actual columns on first run so we can see exactly what the file has
        logger.info("Seed file columns detected", extra={"columns": list(df.columns)})
        self.stdout.write(f"Columns in seed file: {list(df.columns)}")

        for chunk_index, chunk_start in enumerate(range(0, len(df), chunk_size), start=1):
            chunk = df.iloc[chunk_start : chunk_start + chunk_size]
            ok, bad = self._process_chunk(chunk, chunk_index)
            total_ok += ok
            total_bad += bad

        elapsed = time.monotonic() - t_start
        logger.info(
            "seed_data completed",
            extra={
                "total_inserted_or_updated": total_ok,
                "total_skipped_bad_rows": total_bad,
                "elapsed_seconds": round(elapsed, 2),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {total_ok} rows upserted, {total_bad} bad rows skipped ({elapsed:.1f}s)."
            )
        )

    def _normalise_columns(self, chunk: pd.DataFrame) -> pd.DataFrame:
        """Lower-case + strip whitespace, then apply COLUMN_ALIASES."""
        chunk = chunk.copy()
        chunk.columns = [c.lower().strip() for c in chunk.columns]
        return chunk.rename(columns=self.COLUMN_ALIASES)

    def _process_chunk(self, chunk: pd.DataFrame, chunk_index: int):
        now = timezone.now()
        to_upsert = []
        bad = 0

        chunk = self._normalise_columns(chunk)

        for _, row in chunk.iterrows():
            try:
                # ── provider_name ─────────────────────────────────────────────
                provider = str(row.get("provider_name", "")).strip()
                if not provider or provider == "nan":
                    raise ValueError("provider_name is blank or missing")

                # ── rate_type ─────────────────────────────────────────────────
                rate_type = str(row.get("rate_type", "")).strip()
                if not rate_type or rate_type == "nan":
                    raise ValueError("rate_type is blank or missing")

                # ── rate_value ────────────────────────────────────────────────
                raw_val = row.get("rate_value")
                if raw_val is None or (isinstance(raw_val, float) and pd.isna(raw_val)):
                    raise ValueError("rate_value is null")
                rate_value = float(raw_val)
                if rate_value < 0:
                    raise ValueError(f"Negative rate_value: {rate_value}")

                # ── effective_date ────────────────────────────────────────────
                raw_date = row.get("effective_date")
                if raw_date is None:
                    raise ValueError("effective_date is null")
                effective_date = pd.to_datetime(raw_date).date()

                # ── raw_payload: store everything the file gave us ────────────
                # Convert non-JSON-serialisable types (Timestamps, date) -> str
                raw_payload = {}
                for k, v in row.to_dict().items():
                    if isinstance(v, (str, int, float, bool, type(None))):
                        raw_payload[k] = v
                    else:
                        raw_payload[k] = str(v)

                to_upsert.append(
                    Rate(
                        provider_name=provider,
                        rate_type=rate_type,
                        rate_value=rate_value,
                        effective_date=effective_date,
                        ingestion_timestamp=now,
                        raw_payload=raw_payload,
                    )
                )

            except Exception as exc:
                bad += 1
                logger.warning(
                    "Bad row skipped",
                    extra={
                        "chunk": chunk_index,
                        "error": str(exc),
                        "row": str(row.to_dict()),
                    },
                )

        if to_upsert:
            # The seed file contains duplicate (provider, type, date) triples
            # within the same chunk. PostgreSQL ON CONFLICT DO UPDATE cannot
            # affect the same row twice in one statement — deduplicate here,
            # keeping the last occurrence (most recent wins within the chunk).
            seen = {}
            for obj in to_upsert:
                key = (obj.provider_name, obj.rate_type, obj.effective_date)
                seen[key] = obj
            deduped = list(seen.values())

            dupes = len(to_upsert) - len(deduped)
            if dupes:
                logger.info(
                    "Duplicate rows collapsed within chunk",
                    extra={"chunk": chunk_index, "duplicates_removed": dupes},
                )

            with transaction.atomic():
                Rate.objects.bulk_create(
                    deduped,
                    update_conflicts=True,
                    unique_fields=["provider_name", "rate_type", "effective_date"],
                    update_fields=["rate_value", "ingestion_timestamp", "raw_payload"],
                )

        logger.debug(
            "Chunk processed",
            extra={"chunk": chunk_index, "ok": len(to_upsert), "bad": bad},
        )
        return len(to_upsert), bad
