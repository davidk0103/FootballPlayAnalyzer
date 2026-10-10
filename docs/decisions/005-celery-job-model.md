# ADR 005: Celery + Redis background jobs with PostgreSQL as the job ledger

- Status: Accepted
- Date: 2026-10-10

## Context

Season imports take 8 to 15 seconds each (download, validate, upsert about 45k plays)
and can fail in ways worth retrying: GitHub release downloads time out, PostgreSQL
restarts, workers get OOM-killed or redeployed. Users need to start an import from the
UI, see progress, cancel it, and trust that retries never double-import or leave a
half-written season behind. M1's synchronous CLI ([ADR 003](003-sync-ingestion-before-celery.md))
blocks a terminal and has no retry or visibility.

## Decision

1. **Celery with a Redis broker** runs imports. Celery is the standard Python task
   queue, has a prefork pool for CPU-heavy pandas work, and supports the delivery
   guarantees we need (late acks, requeue on worker loss). The Redis instance also
   hosts the analytics cache in a separate logical database.
2. **PostgreSQL is the source of truth for job state**, not Celery's result backend
   (`task_ignore_result=True`). `import_jobs` holds one row per user request;
   `job_attempts` holds one row per execution. Celery messages carry only a job id.
   Broker messages can be lost or duplicated; job rows cannot.
3. **An explicit state machine** (`app/jobs/state.py`) with seven states: `queued`,
   `running`, `retrying`, `cancel_requested`, `succeeded`, `failed`, `cancelled`.
   Every write is a compare-and-set `UPDATE ... WHERE status IN (allowed sources)`,
   with each pair validated against the transition table, so racing writers (API
   cancel, worker, reaper) cannot corrupt state.
4. **At-least-once delivery, made safe by idempotent execution.** `task_acks_late`
   and `task_reject_on_worker_lost` mean a crash causes redelivery rather than a lost
   job. Every delivery takes a per-job PostgreSQL advisory lock, so a duplicate
   delivery is dropped while the original runs. The import itself is idempotent:
   checksum skip, keyed upserts, and **one database transaction per import**.
5. **One transaction per import** (a change from M1's per-chunk commits). Failure,
   cancellation, or a crash rolls back to the previous state, so retries always start
   clean and readers never see a half-imported season. PostgreSQL handles a
   50k-row transaction comfortably; statements stay chunked to bound memory.
6. **Retries are owned by the job runner, not Celery's `autoretry`.** Transient
   errors (network, 5xx/429, DB `OperationalError`, soft timeout) are retried with
   exponential backoff and equal jitter (`delay/2 + U(0, delay/2)`, base 2s, cap 60s)
   up to `max_attempts` (4). Permanent errors (404, validation, code bugs) fail
   immediately. A job that keeps killing its worker is failed as **poison** once its
   attempts are used up, whether the deaths are seen by the runner on redelivery or
   by the reaper.
7. **Crash recovery has two layers.** Celery requeues on pool-process death; a
   **reaper** (on worker start plus every 30s via beat) recovers jobs whose heartbeat
   is stale *and* whose advisory lock is free, and republishes `queued`/`retrying` jobs
   whose message was never published.
8. **Duplicate-submission protection** has two layers: an `Idempotency-Key` (header or
   body; same key + same params replays the original job, different params is a 409),
   and a partial unique index allowing one active job per `(task_type, target_key)`,
   which returns a 409 `duplicate_job` regardless of key.
9. `user_id` is nullable with no foreign key until accounts arrive in M3.

## Alternatives considered

- **FastAPI `BackgroundTasks` / a thread pool:** no durability, no retries, and work
  dies with the API process. Rejected.
- **RQ / Dramatiq / arq:** simpler, but Celery's prefork pool, time limits, beat, and
  `reject_on_worker_lost` cover the crash cases directly, and it is what most Python
  teams run.
- **Postgres-only queue (`SELECT ... FOR UPDATE SKIP LOCKED`):** fewer moving parts and
  transactional enqueue. A strong option; we chose Celery so we can learn and measure
  a broker-based design (M4 benchmarks), and because the cache needs Redis anyway.
- **Celery result backend as job state:** results expire, can't be queried by
  status, and have no attempt history. Rejected in favor of our own tables.
- **Per-chunk commits with resumable progress:** faster recovery for huge files, but
  a retry would see partial state and readers would see half a season. Not worth it
  at about 50k rows.

## Consequences

- Delivery is at-least-once; every effect must be idempotent. New job types must
  follow the same pattern (lease, status re-check, idempotent work, CAS outcome).
- Redis must not evict broker keys: Compose runs `maxmemory-policy volatile-lru`, so
  only TTL'd cache keys are evicted.
- `broker_visibility_timeout_seconds` (1h) must exceed the longest job runtime plus
  retry countdown, or a long job can be redelivered while still running. The
  advisory lock makes that a dropped duplicate, not a double import.
- Exactly one `beat` process may run; worker processes scale freely.
- Documented crash windows (see [architecture](../architecture.md#failure-recovery-and-crash-windows))
  are closed by the reaper rather than by distributed transactions.
