"""
Unit tests for the seed_data ingestion worker.
Uses real temporary Parquet files — no HTTP mocking needed.
 
The real seed file uses column name "provider" not "provider_name".
KNOWN_FIXTURE matches the real file schema so tests reflect production behaviour.
"""
from pathlib import Path
 
import pandas as pd
import pytest
from django.core.management import call_command
 
from rates.models import Rate
 
 
def _make_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write rows to a Snappy-compressed Parquet file and return its path."""
    df = pd.DataFrame(rows)
    path = tmp_path / "rates_seed.parquet"
    df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
    return path
 
 
# Matches the real seed file column schema (provider, not provider_name)
KNOWN_FIXTURE = [
    {
        "provider": "Chase", "rate_type": "mortgage_30yr",
        "rate_value": 6.875, "effective_date": "2024-03-01",
        "ingestion_ts": "2024-03-01 13:00:00", "source_url": "https://chase.com",
        "raw_response_id": "abc-123", "currency": "USD",
    },
    {
        "provider": "WellsFargo", "rate_type": "mortgage_30yr",
        "rate_value": 6.750, "effective_date": "2024-03-01",
        "ingestion_ts": "2024-03-01 13:00:00", "source_url": "https://wf.com",
        "raw_response_id": "def-456", "currency": "USD",
    },
    {
        "provider": "Chase", "rate_type": "savings_1yr",
        "rate_value": 4.100, "effective_date": "2024-03-01",
        "ingestion_ts": "2024-03-01 13:00:00", "source_url": "https://chase.com",
        "raw_response_id": "ghi-789", "currency": "USD",
    },
]
 
 
class TestSeedDataCommand:
    def test_parses_and_inserts_known_fixture(self, db, tmp_path):
        """Parsed output from a known fixture matches expected model fields."""
        path = _make_parquet(tmp_path, KNOWN_FIXTURE)
        call_command("seed_data", file=path, chunk_size=10)
 
        assert Rate.objects.count() == 3
        chase = Rate.objects.get(provider_name="Chase", rate_type="mortgage_30yr")
        assert float(chase.rate_value) == pytest.approx(6.875, rel=1e-4)
        assert str(chase.effective_date) == "2024-03-01"
 
    def test_column_alias_provider_mapped(self, db, tmp_path):
        """'provider' column is correctly mapped to provider_name."""
        path = _make_parquet(tmp_path, KNOWN_FIXTURE)
        call_command("seed_data", file=path)
 
        assert Rate.objects.filter(provider_name="Chase").exists()
        assert Rate.objects.filter(provider_name="WellsFargo").exists()
 
    def test_idempotent_on_second_run(self, db, tmp_path):
        """Running seed_data twice does not duplicate rows."""
        path = _make_parquet(tmp_path, KNOWN_FIXTURE)
        call_command("seed_data", file=path)
        call_command("seed_data", file=path)
 
        assert Rate.objects.count() == 3  # still 3, not 6
 
    def test_handles_duplicate_rows_within_chunk(self, db, tmp_path):
        """Duplicate (provider, type, date) rows in same chunk don't crash."""
        rows = KNOWN_FIXTURE + [
            {
                "provider": "Chase", "rate_type": "mortgage_30yr",
                "rate_value": 6.999, "effective_date": "2024-03-01",
                "ingestion_ts": "2024-03-01 14:00:00", "source_url": "https://chase.com",
                "raw_response_id": "dup-001", "currency": "USD",
            },
        ]
        path = _make_parquet(tmp_path, rows)
        call_command("seed_data", file=path, chunk_size=10)
 
        # Still only 3 unique rows — duplicate collapsed
        assert Rate.objects.count() == 3
 
    def test_skips_null_rate_value_rows(self, db, tmp_path):
        """Rows with null rate_value are skipped without crashing."""
        rows = KNOWN_FIXTURE + [
            {
                "provider": "BadBank", "rate_type": "savings_1yr",
                "rate_value": None, "effective_date": "2024-03-01",
                "ingestion_ts": "2024-03-01 13:00:00", "source_url": "",
                "raw_response_id": "", "currency": "USD",
            },
        ]
        path = _make_parquet(tmp_path, rows)
        call_command("seed_data", file=path)
 
        assert not Rate.objects.filter(provider_name="BadBank").exists()
        assert Rate.objects.count() == 3
 
    def test_skips_negative_rate_value(self, db, tmp_path):
        """Rows with negative rate_value are skipped."""
        rows = KNOWN_FIXTURE + [
            {
                "provider": "NegBank", "rate_type": "mortgage_30yr",
                "rate_value": -0.5, "effective_date": "2024-03-01",
                "ingestion_ts": "2024-03-01 13:00:00", "source_url": "",
                "raw_response_id": "", "currency": "USD",
            },
        ]
        path = _make_parquet(tmp_path, rows)
        call_command("seed_data", file=path)
 
        assert not Rate.objects.filter(provider_name="NegBank").exists()
 
    def test_skip_if_exists_no_ops(self, db, tmp_path, sample_rate):
        """--skip-if-exists does nothing when table is already populated."""
        path = _make_parquet(tmp_path, KNOWN_FIXTURE)
        count_before = Rate.objects.count()
        call_command("seed_data", file=path, skip_if_exists=True)
        assert Rate.objects.count() == count_before
 
    def test_missing_file_exits_nonzero(self, db):
        """Non-existent file raises SystemExit."""
        with pytest.raises(SystemExit):
            call_command("seed_data", file=Path("/nonexistent/path.parquet"))