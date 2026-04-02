# schema.md

Database schema documentation for Rate Tracker.

---

## Tables

### `rates_rate`

The single source of truth for all rate observations. Created by Django migration `0001_initial.py`.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | `bigint` (PK) | No | Auto-incrementing surrogate key |
| `provider_name` | `varchar(255)` | No | Canonical name of the rate provider (e.g. `"Chase"`) |
| `rate_type` | `varchar(100)` | No | Category of rate (e.g. `"mortgage_30yr"`, `"savings_1yr"`) |
| `rate_value` | `numeric(10,6)` | No | Rate as a percentage (e.g. `6.875000` = 6.875%) |
| `effective_date` | `date` | No | Business date the rate was effective |
| `ingestion_timestamp` | `timestamptz` | No | Wall-clock UTC time the row was written |
| `raw_payload` | `jsonb` | Yes | Raw source row stored for replay on failed parses |

**Unique constraint:** `(provider_name, rate_type, effective_date)`

This constraint is the foundation of the idempotency strategy. It ensures that re-running the seed worker or replaying a webhook call cannot create duplicate logical observations.

---

## Indexes

### `idx_provider_type_date`

```sql
CREATE INDEX idx_provider_type_date
    ON rates_rate (provider_name, rate_type, effective_date DESC);
```

**Serves:** `GET /rates/latest` — fetches the most recent rate per (provider, type) pair.

**Query pattern:**
```sql
SELECT DISTINCT ON (provider_name, rate_type)
    provider_name, rate_type, rate_value, effective_date
FROM rates_rate
ORDER BY provider_name, rate_type, effective_date DESC;
```

`DISTINCT ON` requires the `ORDER BY` to lead with the same columns. This index makes that sort a index scan rather than a sequential scan + sort, which matters at ~1M rows.

**Optional `?type=` filter** adds a leading equality predicate — PostgreSQL can use the same index with a partial skip.

---

### `idx_rate_type_date`

```sql
CREATE INDEX idx_rate_type_date
    ON rates_rate (rate_type, effective_date);
```

**Serves:** `GET /rates/history` with `?type=` and date range filters, and any analytical query asking "what did 30yr mortgage rates do over the past 30 days across all providers?"

**Query pattern:**
```sql
SELECT * FROM rates_rate
WHERE rate_type = 'mortgage_30yr'
  AND effective_date BETWEEN '2024-01-01' AND '2024-01-31'
ORDER BY effective_date;
```

A composite index on `(rate_type, effective_date)` allows PostgreSQL to satisfy the equality on `rate_type` and then range-scan on `effective_date` without touching the heap for rows outside the range.

---

### `idx_ingestion_ts`

```sql
CREATE INDEX idx_ingestion_ts
    ON rates_rate (ingestion_timestamp);
```

**Serves:** "All records ingested in a given 24-hour window" — an operational query for monitoring and replay.

**Query pattern:**
```sql
SELECT * FROM rates_rate
WHERE ingestion_timestamp >= '2024-03-01 00:00:00+00'
  AND ingestion_timestamp <  '2024-03-02 00:00:00+00';
```

---

## Tradeoffs considered

**Why a single table?**

A normalised design would split `providers` and `rate_types` into lookup tables and use foreign keys. This has two advantages: referential integrity and smaller row size. I chose a denormalised single table because:

1. Provider names and rate types are low-cardinality, stable strings — no risk of update anomalies in practice.
2. Joining three tables on every `/rates/latest` request adds query complexity for no measurable benefit at the data volume stated.
3. The seed file delivers flat rows; normalisation would require a two-pass ETL.

In production with multiple years of data, I would consider a partial normalisation where `provider_name` becomes a foreign key to a `providers` table, enabling provider-level metadata (logo URL, website, etc.).

**Why `numeric(10,6)` for `rate_value`?**

`float` (IEEE 754) loses precision for decimal fractions like `6.875`. A rate displayed as `6.875%` should store and retrieve as exactly `6.875000`, not `6.87499999...`. `numeric` is the correct type for financial values. The `(10, 6)` precision supports rates up to `9999.999999%` which covers any foreseeable interest rate.

**Why not a time-series database (TimescaleDB, InfluxDB)?**

The data volume (~1M seed rows, growing slowly) does not justify the operational overhead of a specialised TSDB. PostgreSQL with well-chosen indexes answers all three required queries in single-digit milliseconds at this scale. TimescaleDB would be worth considering above ~100M rows or with sub-minute granularity requirements.

**Why `jsonb` for `raw_payload`?**

`jsonb` stores a binary-parsed representation, making it faster to query than `text`. The raw payload column is write-once (set at ingest time, never updated) and only read for replay/debugging, so the slight write overhead of `jsonb` over `text` is irrelevant.

**Index maintenance overhead.**

Three additional indexes on a ~1M-row table add ~15–20% write overhead compared to a heap-only table. Given that writes happen in batch (seed) or one at a time (webhook), and reads are the hot path, this tradeoff strongly favours the indexes.
