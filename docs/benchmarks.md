# Benchmarks (Milestone 4)

All numbers below come from run **`20261011T052922Z`**. Raw JSON lives under
[`benchmarks/results/20261011T052922Z/`](../benchmarks/results/20261011T052922Z/).

## Environment

| Field | Value |
| --- | --- |
| Platform | Linux 6.12.94+ x86_64 (glibc 2.39) |
| CPUs | 4 |
| RAM | 16,014 MB (`MemTotal` from `/proc/meminfo`) |
| Python | 3.12.3 |
| SQLAlchemy | 2.1.4 |
| httpx | 0.28.1 |
| Locust | 2.46.7 |
| API | `http://localhost:8317` (Docker Compose backend) |
| PostgreSQL | 16 via Compose (`localhost:5433`) |
| Redis | 7 via Compose (`localhost:6380`) |
| Celery workers | 1 container × `WORKER_CONCURRENCY=2` prefork processes (unless scaling test says otherwise) |
| Dataset | nflverse 2024 season: **43,110** plays in `plays`; 2023 season: **43,658** plays |

Load averages at capture time were ~1.1–1.9 (1-minute).

## HTTP micro-benchmark (`scripts/bench_http.py`)

Settings: **8** concurrent threads, **12 s** warmup, **25 s** measured per endpoint.

After warmup the analytics cache was **100% HIT** on every endpoint (no misses recorded).

| Endpoint | RPS | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | ---: | ---: | ---: | ---: |
| `team-comparison` | 228.7 | 33.9 | 46.0 | 91.2 |
| `situational` | 236.5 | 32.5 | 44.6 | 93.7 |
| `efficiency` | 244.4 | 31.5 | 43.3 | 92.2 |

Charts: [`docs/benchmarks/charts/http-latency-rps.png`](benchmarks/charts/http-latency-rps.png).

## Locust (`loadtests/locustfile.py`, headless)

Settings: **16** users, spawn **5**/s, **25 s** run, mixed analytics tasks.

| Metric | Value |
| --- | ---: |
| Aggregated RPS | 112.8 |
| Median latency | 8 ms |
| p95 | 18 ms |
| p99 | 28 ms |
| Max | 183 ms |
| Failures | 0 |

Locust percentile table (ms): 50%=8, 75%=10, 90%=15, 95%=18, 99%=28.

## Job throughput (`scripts/bench_jobs.py`)

Settings: **2** sequential `import_season` jobs for **2023**, `force=true`, admin API.

| Metric | Value |
| --- | ---: |
| Queue wait (p50) | 0.52 s |
| End-to-end per job (p50) | 11.58 s |
| Throughput | 10.35 jobs/min |
| Outcomes | 2 × `succeeded` |

Imports were checksum no-ops (play count unchanged at 43,658) but still exercise the full
worker path and transaction.

## Worker scaling (`scripts/bench_workers.py`)

Run **`20261011T054500Z`** (raw:
[`workers.json`](../benchmarks/results/20261011T054500Z/workers.json)). Supersedes the earlier
single-job-per-step run in `20261011T052922Z`, which could not use extra containers.

Settings: **`WORKER_CONCURRENCY=2`** per container. At each scale step, submit **8** import jobs
in one batch (`force=true`), one distinct season each (2016–2023). Wall time is from first
submit until all eight reach a terminal state. Hardware matches the table above (4 CPUs, 16 GB).

| Worker containers | Max processes (containers×2) | Peak jobs running | Batch wall (s) | Jobs/min | Queue wait p50 (s) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 88.53 | 5.42 | 31.53 |
| 2 | 4 | 4 | 92.53 | 5.19 | 11.24 |
| 4 | 8 | 8 | 86.99 | 5.52 | 0.18 |
| 8 | 16 | 8 | 89.02 | 5.39 | 0.17 |

![Worker scaling](benchmarks/charts/worker-scaling.png)

**What this shows**

- With **one container**, only **two** imports run at once (`peak_concurrent_running=2`); the
  other six jobs wait (queue p50 **31.5 s**). Total batch time ~**88.5 s**.
- With **four containers** (eight processes), all **eight** jobs run together (`peak=8`), queue
  waits drop to **&lt;1 s**, and batch time improves slightly to **~87 s** (~2% faster than one
  container).
- **Eight containers** do not beat four: there are only **eight** jobs, so `peak_concurrent_running`
  stays **8** and wall time is again ~**89 s**. More containers than jobs cannot help.

**Why gains are modest overall:** each job is a full-season `force` import (download + pandas +
  single large transaction). Parallelism hides queueing once process count ≥ job count, but total
  work is still eight heavy imports. The **2-container** step was slightly slower than **1** on
  this run (92.5 s vs 88.5 s), likely from container startup overlap and Postgres/Redis
  contention when four imports ran at once—reruns may vary by a few seconds.

Reproduce: `make bench-workers` (needs Docker; clears best with `docker compose exec redis redis-cli -n 1 FLUSHDB` if login is rate-limited after many attempts).

## Database (`EXPLAIN ANALYZE`, `scripts/bench_explain.py`)

| Query | Execution time (ms) |
| --- | ---: |
| `SELECT count(*) FROM plays WHERE season = 2024` | 4.29 |
| `SELECT … FROM plays WHERE season = 2024 LIMIT 50000` | 11.48 |
| Latest row in `datasets` for season | 0.03 |
| Queue depth `jobs` grouped by status | 0.06 |

The 50k-row scan uses an index on `season` but still reads many heap pages; analytics load the
full season into pandas once per cache miss, which dominates API latency on cold cache (not
shown in the HTTP table above because warmup kept cache at HIT).

Full plans: [`explain.json`](../benchmarks/results/20261011T052922Z/explain.json).

## How to reproduce

```bash
make up && make migrate && make ingest SEASONS=2023,2024
make admin EMAIL=admin@playbookiq.test   # set password when prompted
export BENCH_RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
export DATABASE_URL=postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq
make bench                    # explain + http + locust + jobs + charts
make bench-workers            # parallel import batch, scales 1/2/4/8 containers (slow; Docker)
make observability            # Prometheus :9090, Grafana :3000 (admin / playbookiq)
```

Locust UI: `cd backend && uv run locust -f loadtests/locustfile.py --host http://localhost:8317`.
