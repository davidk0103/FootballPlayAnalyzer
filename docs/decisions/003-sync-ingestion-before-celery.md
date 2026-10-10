# ADR 003: Synchronous ingestion CLI before Celery

- Status: Accepted
- Date: 2026-10-10

## Context

Imports will eventually run as background jobs (Celery + Redis, M2) with retries,
cancellation, and a job dashboard. M1 only needs two seasons loaded once.

## Decision

M1 ships `python -m app.ingest`, a synchronous CLI that calls
`app.ingest.service.ingest_season()`. The M2 Celery task will call the same
function.

## Consequences

- Core ingestion logic (checksum, validation, chunked upsert, quarantine) is
  written and tested once.
- Idempotency is already required in M1: a file whose SHA-256 matches a completed
  dataset is skipped, and play upserts are keyed on `(game_id, external_play_id)`.
- No job table yet; `datasets.status` records `completed` or `failed`.

> Update (M2): the Celery task now calls `ingest_season()` as planned. Per-chunk commits
> were replaced by a single transaction per import; see [ADR 005](005-celery-job-model.md).
