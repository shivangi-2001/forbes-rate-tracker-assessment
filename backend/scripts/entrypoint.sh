#!/bin/sh
set -e

# Fail fast on missing required env vars
: "${SECRET_KEY:?SECRET_KEY is required}"
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${INGEST_API_KEY:?INGEST_API_KEY is required}"

echo "[entrypoint] Waiting for database..."
python - <<'EOF'
import os, time, psycopg2
url = os.environ["DATABASE_URL"]
for i in range(30):
    try:
        psycopg2.connect(url)
        print("[entrypoint] Database ready.")
        break
    except psycopg2.OperationalError:
        print(f"[entrypoint] DB not ready, retry {i+1}/30...")
        time.sleep(2)
else:
    print("[entrypoint] Database never became ready — exiting.")
    exit(1)
EOF

echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput --clear

exec "$@"
