.PHONY: help up down build seed test logs shell lint migrate

# ── Colours ───────────────────────────────────────────────────────────────────
CYAN  := \033[0;36m
RESET := \033[0m

help: ## Show this help message
	@echo ""
	@echo "  Rate Tracker — available commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-18s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ── Docker lifecycle ──────────────────────────────────────────────────────────
up: ## Start the full stack (build if needed)
	docker compose up --build -d
	@echo "$(CYAN)Dashboard:$(RESET) http://localhost:3000"
	@echo "$(CYAN)API:$(RESET)       http://localhost:8000/api/rates/latest"

down: ## Stop and remove containers (keeps volumes)
	docker compose down

build: ## Build all images without starting
	docker compose build

restart: ## Restart a single service  e.g. make restart svc=api
	docker compose restart $(svc)

# ── Data ─────────────────────────────────────────────────────────────────────
seed: ## Load rates_seed.parquet into the database (idempotent)
	docker compose exec api python manage.py seed_data
	@echo "$(CYAN)Seed complete.$(RESET)"

seed-custom: ## Seed from a custom file  e.g. make seed-custom file=/data/custom.parquet
	docker compose exec api python manage.py seed_data --file $(file)

# ── Testing ───────────────────────────────────────────────────────────────────
test: ## Run the full pytest suite inside the api container
	docker compose run --rm api pytest

test-verbose: ## Run tests with full output
	docker compose run --rm api pytest -v --tb=long

test-unit: ## Run only unit tests (ingestion)
	docker compose run --rm api pytest tests/test_ingestion.py -v

test-api: ## Run only API integration tests
	docker compose run --rm api pytest tests/test_api.py -v

# ── Logs ─────────────────────────────────────────────────────────────────────
logs: ## Tail logs for all services
	docker compose logs -f

logs-api: ## Tail API logs only
	docker compose logs -f api

logs-celery: ## Tail Celery worker logs
	docker compose logs -f celery_worker

logs-beat: ## Tail Celery beat logs
	docker compose logs -f celery_beat

# ── Django helpers ────────────────────────────────────────────────────────────
shell: ## Open a Django shell
	docker compose exec api python manage.py shell

migrate: ## Run Django migrations
	docker compose exec api python manage.py migrate

createsuperuser: ## Create a Django admin superuser
	docker compose exec api python manage.py createsuperuser

# ── Code quality ──────────────────────────────────────────────────────────────
lint: ## Run ruff linter on backend
	docker compose run --rm api ruff check .

format: ## Auto-format backend code with ruff
	docker compose run --rm api ruff format .
