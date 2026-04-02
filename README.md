# Rate Tracker

A production-shaped full-stack application that scrapes, stores, exposes, and visualises interest-rate data.

**Stack:** Django · PostgreSQL · Redis · Celery · Next.js · Docker Compose

**video link** 
```
https://drive.google.com/drive/folders/1TTuUF2U4-PiaUnCFqO6kkURedrkLU7Hm?usp=sharing

```

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Docker | 24+ |
| Docker Compose | v2.24+ (bundled with Docker Desktop) |
| Make | any |


---

## Running locally

### 1. Clone and configure environment

```bash
git clone https://github.com/shivangi-2001/forbes-rate-tracker-assessment.git
cd forbes-rate-tracker-assessment
cp .env.example .env
```

Edit `.env` and set real values for:

- `SECRET_KEY` — generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `INGEST_API_KEY` — generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### 2. Start the full stack

```bash
make up
```

This builds all images and starts: PostgreSQL, Redis, Django API, Celery worker, Celery beat scheduler, and the Next.js dashboard.

The dashboard is available at **http://localhost:3000** within ~2 minutes of running `make up`.
The API is available at **http://localhost:8000/api**.

### 3. Seed the database

**(Important)** Place `rates_seed.parquet` into `backend/data/`, then run:

```bash
make seed
```

The seed command is fully idempotent — running it multiple times will not create duplicate rows.

---

## Running tests

```bash
make test           # full suite
make test-unit      # ingestion worker tests only
make test-api       # API integration tests only
make test-verbose   # with full tracebacks
```

---

## API reference

All endpoints are prefixed with `/api`.

### `GET /api/rates/latest`

Returns the most recent rate per provider. Cached in Redis for 5 minutes.

Query params:
- `?type=mortgage_30yr` — filter by rate type (optional)

### `GET /api/rates/history`

Returns paginated time-series for a provider + type combination.

Query params (all required unless noted):
- `provider=Chase`
- `type=mortgage_30yr`
- `from=2024-01-01` (optional)
- `to=2024-03-31` (optional)
- `page=1` (optional, default 1)

### `POST /api/rates/ingest`

Authenticated webhook. Accepts a single rate record, validates it, writes to the DB, and busts the relevant cache keys.

Headers: `Authorization: Bearer <INGEST_API_KEY>`

Body:
```json
{
  "provider_name": "Chase",
  "rate_type": "mortgage_30yr",
  "rate_value": "6.875",
  "effective_date": "2024-07-01",
  "ingestion_timestamp": ... ,
  "raw_payload": ...,
}
```

Returns `201 Created` on insert, `200 OK` on update UNIQUE constraint (same provider + type + date).

---

## Useful commands

```bash
make up             # Start the full stack (build if needed)
make down           # Stop and remove containers (keeps volumes)
make build          # Build all images without starting
make logs           # tail all service logs
make logs-api       # tail Django logs only
make logs-celery    # tail Celery worker logs
make shell          # open Django shell
make migrate        # run migrations manually
make down           # stop all containers
```

---

## Project structure

```
rate-tracker/
├── backend/
│   ├── config/            # Django project (settings, urls, celery)
│   ├── rates/             # App: models, views, serializers, tasks
│   │   ├── management/commands/seed_data.py
│   │   └── migrations/
│   ├── tests/             # pytest suite
│   ├── data/              # Mount point for rates_seed.parquet
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/           # Next.js App Router pages
│   │   ├── components/    # RatesTable, RateHistoryChart
│   │   ├── hooks/         # useAutoRefresh
│   │   └── lib/           # API client (typed)
│   └── Dockerfile
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Makefile
├── .env.example
├── README.md
├── DECISIONS.md
└── schema.md
```

---

## AI tools used

Claude (Anthropic) was used to:
- Generate pytest suite
- Generate GitHub Actions CI/CD pipeline

Warp Terminal:
- For command-line generate and debug

ChatGpt:
- for Next.js Debugging issue

Cursor for IDE

All generated code was reviewed, understood, and adapted. 

Schema Design, idempotency strategy (upsert on unique constraint), index choices, cache invalidation approach, and DECISIONS.md reasoning are the author's own engineering decisions.

## Author

**Shivangi Keshri**
***shivangikeshri21@gmail.com***
