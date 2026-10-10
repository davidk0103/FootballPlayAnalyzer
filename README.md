# PlaybookIQ

Football analytics on real NFL play-by-play data from [nflverse](https://github.com/nflverse/nflverse-data).
Pick two teams and a season, slice by down, distance, field position, quarter, and play
type, and compare EPA per play, success rate, third-down conversion, explosive plays,
yards per play, pass rate, and turnovers, with every metric showing its numerator,
denominator, and sample size. Import any season from 1999 on as a background job and
watch it run on the Jobs dashboard.

Status: **Milestone 2** (Celery background imports with retries and crash recovery,
Redis analytics cache, Jobs dashboard), on top of Milestone 1 (ingestion, analytics API,
compare page).

| Layer | Stack |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pandas + pyarrow, uv |
| Jobs and cache | Celery 5 (prefork workers + beat), Redis 7 |
| Database | PostgreSQL 16 (data and job state) |
| Frontend | Vite, React 19, TypeScript (strict), Tailwind v4, shadcn/ui, TanStack Query, Recharts, React Hook Form + Zod |
| Tests | pytest (unit + integration against real Postgres, Redis, and a real Celery worker), Vitest + RTL + MSW, Playwright |
| Ops | Docker Compose with healthchecks, Makefile, GitHub Actions |

## Quick start (Docker)

Requires Docker with Compose v2.

```bash
cp .env.example .env            # optional; every value has a default
make up                         # db, redis, backend, worker, beat, frontend; waits for healthy
make migrate                    # alembic upgrade head
make ingest SEASONS=2023,2024   # synchronous CLI import: ~20 MB/season, ~10 s/season
```

Open <http://localhost:5317/compare?team_a=KC&team_b=PHI&season=2024>.
API docs: <http://localhost:8317/docs>.

To import in the background instead, open <http://localhost:5317/jobs> and queue a
season, or run `make import-job SEASON=2022`. Jobs retry transient failures with
backoff, survive worker crashes, can be cancelled (the import rolls back), and refresh
the analytics cache when they finish.

Re-running an import is safe: a file whose SHA-256 matches a completed import is
skipped, plays are upserted on `(game_id, play_id)`, and each import is one transaction.

Scale workers with `make scale-workers WORKERS=4` (containers) and
`WORKER_CONCURRENCY` (processes per container); see
[architecture: scaling](docs/architecture.md#scaling-workers-processes-vs-concurrency).

## Local development (no Docker for the app)

Requires [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16, and Redis 7
(`docker compose up -d db redis` gives you both on ports 5433 and 6380).

```bash
make install
cd backend
export DATABASE_URL=postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq
export BROKER_URL=redis://localhost:6380/0 CACHE_URL=redis://localhost:6380/1
uv run alembic upgrade head
uv run python -m app.ingest --seasons 2023,2024
uv run uvicorn app.main:app --port 8317 --reload

# in a second terminal (same env vars): the background worker and reaper schedule
uv run celery -A app.worker.celery_app worker --concurrency=2 --loglevel=INFO
uv run celery -A app.worker.celery_app beat

# in a third terminal
cd frontend && npm run dev      # http://localhost:5317, proxies /api to :8317
```

The API works without Redis: analytics are served uncached (`X-Cache: DEGRADED`) and
submitted jobs wait in `queued` until a broker and worker are available.

## Make targets

| Target | What it does |
| --- | --- |
| `make up` / `make down` | Start / stop the Compose stack |
| `make migrate` | Apply Alembic migrations in the backend container |
| `make ingest SEASONS=2023,2024` | Import seasons synchronously (CLI) in the backend container |
| `make import-job SEASON=2022` | Queue a background import through the API |
| `make scale-workers WORKERS=4` | Run N worker containers (1/2/4/8 tested) |
| `make worker-logs` / `make reap-jobs` | Tail worker + beat logs / run the stale-job reaper now |
| `make test` | Start the disposable test DB (5434) and Redis (6381), run backend (incl. real worker) and frontend tests |
| `make e2e` | Playwright happy path (reuses servers on 8317/5317 or starts them) |
| `make lint` / `make typecheck` | ruff + oxlint / mypy strict + tsc strict |
| `make profile` | Re-profile the nflverse files and refresh `docs/data.md` |
| `make gen-api` | Regenerate `frontend/openapi.json` and the TypeScript API types |

## Repository layout

```
backend/
  app/
    api/           routes, dependencies, error envelope (no business logic)
    services/      orchestration and response envelopes
    repositories/  SQLAlchemy queries
    analytics/     pure pandas metric and filter functions
    ingest/        nflverse download, validation, chunked upserts, CLI
    jobs/          job state machine, submit/cancel, runner, reaper, leases, heartbeats
    worker/        Celery app and tasks
    cache.py       Redis analytics cache
    models/        SQLAlchemy models
  alembic/         migrations
  scripts/         profile_pbp.py, export_openapi.py, make_test_fixture.py
  tests/           unit/, integration/, fixtures/ (trimmed real nflverse sample)
frontend/
  src/pages/       LandingPage, ComparePage, JobsPage
  src/features/compare/  pickers, filters, metric cards, chart, definitions
  src/features/jobs/     import form, status badges, attempt history
  src/services/    typed API client + generated OpenAPI types
  e2e/             Playwright tests
docs/              architecture, data, API, ADRs
```

## Documentation

- [Architecture](docs/architecture.md)
- [Data: source, profiling findings, definitions](docs/data.md)
- [API](docs/api.md)
- [Decisions (ADRs)](docs/decisions/)

## Data attribution

Play-by-play data courtesy of the nflverse project (nflfastR / nflreadr). The nflfastR
code is MIT licensed; the nflverse-data repository does not state a data license and the
data originates from NFL sources. PlaybookIQ is a non-commercial, educational portfolio
project and is not affiliated with the NFL. See `docs/data.md`.
