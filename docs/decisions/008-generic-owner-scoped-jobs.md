# ADR 008: Generalize jobs to several task types with owner scoping

- Status: Accepted
- Date: 2026-10-11

## Context

M2's job system ([ADR 005](005-celery-job-model.md)) ran one task: season imports. M3
adds upload processing, report generation, and report exports, all of which need the
same guarantees (at-least-once delivery, leases, heartbeats, retries, cancellation,
idempotency keys). The new jobs belong to a user; season imports affect everyone.

## Decision

- Keep one `jobs` table and one runner. A job has a `task_type` (`import_season`,
  `import_upload`, `generate_report`, `export_report`), JSON `params`, an optional
  `user_id`, and an optional `target_key` (for example `season:2024`, `upload:{id}`,
  `report:{id}`). A partial unique index on `target_key` for active jobs prevents two
  concurrent jobs on the same target (409 `duplicate_job` / `upload_busy`).
- Handlers implement one contract (`app/jobs/handler_types.py`): they receive the job
  and a `checkpoint(stage, done, total)` callback that records progress, honors
  cancellation, and heartbeats. `HANDLERS` maps task type to handler. Each handler may
  return an `after_success` hook (for example, delete the processed upload file).
- **Owner scoping.** `GET /jobs` shows a user their own jobs plus public season imports;
  `GET /jobs/{id}` for someone else's job is 404. Cancelling requires ownership (or
  admin).
- **Season imports are admin-only** (403 `admin_required`), since they change data every
  user sees. Admins are created with `python -m app.auth create-admin`.
- Idempotency-Key replay works across task types via `find_by_idempotency_key`. A
  replay returns the original job; a reused key with different parameters is 409.

## Consequences

- One place to reason about failure handling; the M2 crash-recovery tests cover every
  task type.
- Progress is uniform, so the UI uses one `JobProgress` component.
- Domain objects keep their own status (`user_datasets.status`, `saved_reports.status`).
  A lazy `_reconcile` on read marks them failed if their job failed or was cancelled,
  so they cannot get stuck in `processing` / `pending`.

## Alternatives considered

- **A table per job type.** Duplicates the state machine and recovery logic.
- **Plain Celery tasks for the small jobs.** Loses retries, visibility, and cancellation
  that users see on the upload and report pages.
