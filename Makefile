SEASONS ?= 2023,2024
COMPOSE ?= docker compose
TEST_DATABASE_URL ?= postgresql+psycopg://playbookiq:playbookiq@localhost:5434/playbookiq_test
UV ?= uv

.PHONY: help up down logs migrate ingest profile test test-db test-backend test-frontend \
	e2e lint format typecheck gen-api install

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

# --- Docker stack -----------------------------------------------------------
up: ## Build and start db, backend, frontend (waits for healthchecks)
	$(COMPOSE) up -d --build --wait db backend frontend

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

logs: ## Tail stack logs
	$(COMPOSE) logs -f

migrate: ## Apply database migrations (alembic upgrade head)
	$(COMPOSE) exec backend alembic upgrade head

ingest: ## Import nflverse seasons, e.g. make ingest SEASONS=2023,2024
	$(COMPOSE) exec backend python -m app.ingest --seasons $(SEASONS)

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
test-db: ## Start the disposable test database (port 5434)
	$(COMPOSE) --profile test up -d --wait db-test

test-backend: ## Backend unit + integration tests (needs TEST_DATABASE_URL)
	cd backend && TEST_DATABASE_URL=$(TEST_DATABASE_URL) $(UV) run pytest

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
