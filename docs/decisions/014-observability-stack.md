# ADR 014: Observability stack (M4)

## Status

Accepted (Milestone 4).

## Context

Operators need to see whether the API and workers are healthy under load: request rates,
latencies, cache effectiveness, database cost, and job queue behavior. Logs must be
machine-parseable and safe (no passwords, tokens, or uploaded file contents).

## Decision

1. **Structured JSON logs** on stdout with `request_id` and `job_id` from context vars,
   plus redaction of known secret field names and bearer tokens.
2. **Prometheus metrics** via `prometheus-client`, scraped from `GET /metrics` on the API.
   HTTP metrics use route templates (not raw URLs) to bound cardinality. Queue depth is
   refreshed on each scrape from PostgreSQL and the Celery Redis list.
3. **Grafana** behind a Docker Compose `observability` profile, with a provisioned
   PlaybookIQ dashboard and Prometheus datasource.
4. **Load tests** with Locust (`backend/loadtests/locustfile.py`) and repeatable benchmark
   scripts under `backend/scripts/bench_*.py` that write raw JSON to `benchmarks/results/`.

## Consequences

- Celery workers configure the same JSON logging on `worker_process_init`.
- Analytics cache outcomes increment `piq_cache_lookups_total` in addition to the existing
  Redis hash stats API.
- Benchmark numbers are always tied to a captured environment snapshot (CPU count, memory,
  versions, dataset play counts) and are never hand-edited into docs.
