# DECISIONS.md

Engineering thinking record for the Rate Tracker assessment.

---

## 1. Assumptions

**For Data seeding:** The seed file (`rates_seed.parquet`) have each row represents a rate observation for a (provider, type, date) triple. 
I assumed `effective_date` is the business key, not a wall-clock timestamp, so two rows with the same provider + type + date represent the same logical fact, not two separate events.
``unique_together = ("provider_name", "rate_type", "effective_date")``

**Provider names are canonical strings.** I assumed they arrive pre-normalised (no case variation, no trailing whitespace) from the seed file, so I apply only a `.strip()` on ingest rather than a full normalisation pipeline. In production I would verify this with the data team before deploying.

**Rate values are always percentages expressed as decimals** (e.g. `6.875` means 6.875%). I validated non-negative values; I did not cap them at 100% because some index rates (e.g. SOFR spreads) can theoretically exceed 100bp in unusual markets.

**All timestamps are UTC.** The app sets `CELERY_TIMEZONE = "UTC"` and stores `ingestion_timestamp` as UTC. If source data ever carries timezone-aware dates, conversion to UTC must happen at the serializer boundary.

**The `rates_seed.parquet` file lives at `backend/data/rates_seed.parquet`.** This path is the Docker volume mount point documented in `docker-compose.yml`. A reviewer must place the file there before running `make seed`.

---

## 2. Idempotency strategy

The seed file contains multiple data issues: ``duplicate rows``, null `rate_value` fields, and malformed date strings.

**1. Primary mechanism: Database idempotency technique (UPSERT & UNIQUE).**

The `Rate` model carries a `unique_together` constraint on `(provider_name, rate_type, effective_date)`. The `seed_data` command uses Django's `bulk_create` with `update_conflicts=True`:

```python
Rate.objects.bulk_create(
    to_upsert,
    update_conflicts=True,
    unique_fields=["provider_name", "rate_type", "effective_date"],
    update_fields=["rate_value", "ingestion_timestamp", "raw_payload"],
)
```

This compiles to a single `INSERT ... ON CONFLICT (provider_name, rate_type, effective_date) DO UPDATE SET ...` per batch. Running `seed_data` twice produces identical row counts — the second run is a no-op for valid rows.

**2. Per-processing data value validation handler.**

Before batching, each row passes a validation gate inside `_process_chunk`:
- Null or NaN `rate_value` → skip, log `WARNING`
- Negative `rate_value` → skip, log `WARNING`
- Blank `provider_name` or `rate_type` → skip, log `WARNING`
- Unparseable `effective_date` → skip, log `WARNING`

Bad rows never crash the worker — they are counted and reported in the final summary. The raw payload is stored in `raw_payload (JSONB)` for every valid row so that failed parses can be replayed once the data issue is fixed upstream.

**Webhook idempotency (`POST /rates/ingest`).**

The ingest endpoint uses `update_or_create` on the same unique triple. A second POST with identical payload returns `200 OK` rather than `201 Created`, so clients can safely retry on network failure.

---

## 3. One conscious tradeoff: polling refresh vs. WebSocket

**I chose 60-second client-side polling over a WebSocket push channel.**

Option A (chosen) — `setInterval` + `fetch` in React, 60s:
- Zero additional server infrastructure
- Works with Next.js App Router out of the box
- Trivially testable — mock `fetch` and advance timers
- Meets the spec requirement exactly

Option B (deferred) — Django Channels + WebSocket:
- Push latency drops from up to 60s to sub-second
- Eliminates redundant polling when data has not changed
- Requires adding `channels`, `daphne`, and a channel layer (Redis) to the stack
- Adds ~4–6 hours of correct async configuration and integration testing

Within a 48-hour window, WebSockets would consume roughly 20% of total available time for a benefit (lower staleness) that the spec does not require. Polling is the correct scope-constrained choice. See "one thing I would change" below.

**Cache invalidation strategy for `/rates/latest`.**

I use a 5-minute `TTL` with `cache-asides` strategy as the primary mechanism, with explicit `cache.delete(key)` calls in the `POST /rates/ingest` view as a secondary mechanism. This means:

- Stale reads are bounded to 5 minutes in the worst case
- A webhook POST immediately busts the cache for that rate type, so the next GET sees fresh data within milliseconds

I considered event-driven invalidation only (no TTL) but rejected it: if Celery fails to deliver the invalidation signal, the cache would be stale indefinitely. TTL as a safety net is the right call.

---

## 4. One thing I would change with more time

**Replace the 60-second polling with a Django Channels WebSocket.**

Concretely: after `POST /rates/ingest` writes a new row and invalidates the cache, it would publish an event to a Redis channel group. The Next.js client would hold an open `WebSocket` connection; on receiving the event it would re-fetch `/rates/latest` (or receive the payload directly in the message). The dashboard would update within ~500ms of new data arriving rather than within 60s.

This matters in practice: if a rate moves sharply (e.g. a Fed announcement), a 60-second lag means users are looking at stale data during the most important window.

The change requires:
1. `pip install channels daphne`
2. Configure `CHANNEL_LAYERS` in settings pointing at Redis
3. Replace `gunicorn` with `daphne` in the API container command
4. Add a `consumers.py` WebSocket consumer in the `rates` app
5. Replace `setInterval` in `useAutoRefresh` with a `useWebSocket` hook

Estimated effort: 6–8 hours including tests.
