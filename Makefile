SEASONS ?= 2023,2024
COMPOSE ?= docker compose
TEST_DATABASE_URL ?= postgresql+psycopg://playbookiq:playbookiq@localhost:5434/playbookiq_test
TEST_REDIS_URL ?= redis://localhost:6381
WORKERS ?= 1
FORCE ?= false
UV ?= uv

.PHONY: help up down logs migrate ingest admin import-job scale-workers worker-logs reap-jobs \
	observability profile test test-db test-backend test-frontend e2e lint format typecheck gen-api install \
	bench-http bench-jobs bench-workers bench-explain bench-plot bench

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

# --- Docker stack -----------------------------------------------------------
up: ## Build and start the stack: db, redis, backend, worker, beat, frontend
	$(COMPOSE) up -d --build --wait db redis backend worker beat frontend

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

logs: ## Tail stack logs
	$(COMPOSE) logs -f

migrate: ## Apply database migrations (alembic upgrade head)
	$(COMPOSE) exec backend alembic upgrade head

ingest: ## Import seasons synchronously via the CLI, e.g. make ingest SEASONS=2023,2024
	$(COMPOSE) exec backend python -m app.ingest --seasons $(SEASONS)

admin: ## Create (or promote) an admin account, e.g. make admin EMAIL=you@example.com
	$(COMPOSE) exec backend python -m app.auth create-admin --email $(EMAIL)

import-job: ## Queue an import as an admin: make import-job SEASON=2024 EMAIL=you@example.com
	@test -n "$(EMAIL)" || { echo "EMAIL is required (an admin account; see make admin)"; exit 1; }
	@jar=$$(mktemp); trap 'rm -f $$jar' EXIT; \
	read -rsp "Password for $(EMAIL): " pw; echo; \
	curl -sf -c $$jar -X POST localhost:8317/api/v1/auth/login -H 'X-PlaybookIQ-CSRF: 1' \
		-H 'Content-Type: application/json' \
		-d "{\"email\": \"$(EMAIL)\", \"password\": \"$$pw\"}" > /dev/null \
		|| { echo "login failed"; exit 1; }; \
	curl -s -b $$jar -X POST localhost:8317/api/v1/jobs/import -H 'X-PlaybookIQ-CSRF: 1' \
		-H 'Content-Type: application/json' -d '{"season": $(SEASON), "force": $(FORCE)}'; echo

scale-workers: ## Run N worker containers, e.g. make scale-workers WORKERS=4
	$(COMPOSE) up -d --wait --scale worker=$(WORKERS) worker

worker-logs: ## Tail worker and beat logs
	$(COMPOSE) logs -f worker beat

reap-jobs: ## Run the stale-job reaper once, now
	$(COMPOSE) exec worker python -c "from app.worker.tasks import reap_stale_jobs_task as t; print(t())"

observability: ## Start Prometheus and Grafana (compose profile observability)
	$(COMPOSE) --profile observability up -d --wait prometheus grafana

# --- Local development (no Docker) ------------------------------------------
install: ## Install backend and frontend dependencies locally
	cd backend && $(UV) sync
	cd frontend && npm ci

profile: ## Re-profile nflverse files and refresh docs/data.md
	cd backend && $(UV) run python -m scripts.profile_pbp --seasons $(SEASONS) --docs ../docs/data.md

gen-api: ## Regenerate frontend/openapi.json and TypeScript API types
	cd backend && $(UV) run python -m scripts.export_openapi ../frontend/openapi.json
	cd frontend && npm run gen:api

# --- Quality ------------------------------------------------------------------
test-db: ## Start the disposable test database (5434) and Redis (6381)
	$(COMPOSE) --profile test up -d --wait db-test redis-test

test-backend: ## Backend unit + integration tests, including a real Celery worker
	cd backend && TEST_DATABASE_URL=$(TEST_DATABASE_URL) TEST_REDIS_URL=$(TEST_REDIS_URL) $(UV) run pytest

test-frontend: ## Frontend unit/component tests
	cd frontend && npm test

test: test-db test-backend test-frontend ## All unit and integration tests

e2e: ## Playwright happy path (starts or reuses API on 8317 and Vite on 5317)
	cd frontend && npx playwright test

lint: ## Ruff + oxlint
	cd backend && $(UV) run ruff format --check . && $(UV) run ruff check .
	cd frontend && npm run lint

format: ## Auto-format backend code
	cd backend && $(UV) run ruff format . && $(UV) run ruff check --fix .

typecheck: ## mypy (strict) + tsc (strict)
	cd backend && $(UV) run mypy app scripts tests
	cd frontend && npm run typecheck

# --- Benchmarks (record real numbers; see docs/benchmarks.md) ---------------
bench-http: ## HTTP RPS/latency against localhost:8317
	cd backend && BENCH_RUN_ID=$$(date -u +%Y%m%dT%H%M%SZ) $(UV) run python -m scripts.bench_http

bench-jobs: ## Queue admin import jobs and measure throughput
	cd backend && BENCH_RUN_ID=$$(date -u +%Y%m%dT%H%M%SZ) $(UV) run python -m scripts.bench_jobs

bench-workers: ## Scale workers 1/2/4/8 and measure parallel imports (Docker)
	cd backend && BENCH_RUN_ID=$$(date -u +%Y%m%dT%H%M%SZ) $(UV) run python -m scripts.bench_workers

bench-explain: ## EXPLAIN ANALYZE for analytics queries
	cd backend && BENCH_RUN_ID=$$(date -u +%Y%m%dT%H%M%SZ) $(UV) run python -m scripts.bench_explain

bench-locust: ## Locust headless load test against localhost:8317
	cd backend && BENCH_RUN_ID=$$(date -u +%Y%m%dT%H%M%SZ) $(UV) run python -m scripts.bench_locust

bench-plot: ## Render charts from the latest benchmarks/results run
	cd backend && $(UV) run python -m scripts.bench_plot

bench: bench-explain bench-http bench-locust bench-jobs bench-plot ## Local suite (no worker scaling)
