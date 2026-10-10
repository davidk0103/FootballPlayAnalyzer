# PlaybookIQ

Football analytics on real NFL play-by-play data from [nflverse](https://github.com/nflverse/nflverse-data).
Pick two teams and a season, slice by down, distance, field position, quarter, and play
type, and compare EPA per play, success rate, third-down conversion, explosive plays,
yards per play, pass rate, and turnovers, with every metric showing its numerator,
denominator, and sample size.

Status: **Milestone 1** (ingestion, analytics API, compare page). Seasons 2023 and 2024.

| Layer | Stack |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pandas + pyarrow, uv |
| Database | PostgreSQL 16 |
| Frontend | Vite, React 19, TypeScript (strict), Tailwind v4, shadcn/ui, TanStack Query, Recharts, React Hook Form + Zod |
| Tests | pytest (unit + integration against real Postgres), Vitest + RTL + MSW, Playwright |
| Ops | Docker Compose with healthchecks, Makefile, GitHub Actions |

## Quick start (Docker)

Requires Docker with Compose v2.

```bash
cp .env.example .env            # optional; every value has a default
make up                         # builds and starts db, backend, frontend; waits for healthy
make migrate                    # alembic upgrade head
make ingest SEASONS=2023,2024   # downloads ~20 MB/season from nflverse, ~10 s/season
```

Open <http://localhost:5317/compare?team_a=KC&team_b=PHI&season=2024>.
API docs: <http://localhost:8317/docs>.

Re-running `make ingest` is safe: a file whose SHA-256 matches a completed import is
skipped, and plays are upserted on `(game_id, play_id)`.

## Local development (no Docker for the app)

Requires [uv](https://docs.astral.sh/uv/), Node 22, and a PostgreSQL 16 database
(`docker compose up -d db` gives you one on port 5433).

```bash
make install
cd backend
export DATABASE_URL=postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq
uv run alembic upgrade head
uv run python -m app.ingest --seasons 2023,2024
uv run uvicorn app.main:app --port 8317 --reload

# in another terminal
cd frontend && npm run dev      # http://localhost:5317, proxies /api to :8317
```

## Make targets

| Target | What it does |
| --- | --- |
| `make up` / `make down` | Start / stop the Compose stack |
| `make migrate` | Apply Alembic migrations in the backend container |
| `make ingest SEASONS=2023,2024` | Import nflverse seasons in the backend container |
| `make test` | Start the disposable test DB (port 5434), run backend and frontend tests |
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
    models/        SQLAlchemy models
  alembic/         migrations
  scripts/         profile_pbp.py, export_openapi.py, make_test_fixture.py
  tests/           unit/, integration/, fixtures/ (trimmed real nflverse sample)
frontend/
  src/pages/       LandingPage, ComparePage
  src/features/compare/  pickers, filters, metric cards, chart, definitions
  src/services/    typed API client + generated OpenAPI types
  e2e/             Playwright test
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
