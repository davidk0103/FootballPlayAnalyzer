"""Executes one delivery of a job (any task type). Called by the Celery tasks.

Delivery is at-least-once, so this function must be safe to run any number of times
for the same job:

1. Take the job's advisory-lock lease; if another process holds it, this is a
   duplicate delivery and we drop it.
2. Re-read the job. Terminal jobs are left alone; a pending cancellation is honored.
3. Count the attempt (exhausted attempts = poison job -> FAILED), record it, and run
   the task type's handler with heartbeat + cancel/progress checkpoints.
4. Record the outcome with compare-and-set updates, schedule a retry with backoff for
   transient errors, and run the handler's post-success hooks (e.g. cache invalidation).
"""

import logging
import os
import socket
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.jobs import repository as repo
from app.jobs.errors import JobCancelledError, PermanentJobError, describe, is_transient
from app.jobs.handlers import HANDLERS, Checkpoint
from app.jobs.heartbeat import Heartbeat
from app.jobs.locks import job_lease
from app.jobs.state import TERMINAL, AttemptStatus, JobStatus, backoff_seconds
from app.models import Job, JobAttempt
from app.observability.context import bind_job_id, clear_job_id
from app.observability.metrics import JOB_DURATION, JOBS_FINISHED, JOBS_STARTED

log = logging.getLogger(__name__)

EnqueueRetry = Callable[[uuid.UUID, str, float, int], None]


@dataclass(frozen=True)
class RunOutcome:
    result: str
    retry_in: float | None = None


def worker_name() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _now() -> datetime:
    return datetime.now(UTC)


def _start_attempt(job_id: uuid.UUID) -> tuple[RunOutcome | None, Job | None, int]:
    """Validate state and open a new attempt. Returns an early outcome if no work is due."""
    with get_sessionmaker()() as s:
        job = repo.get_job(s, job_id)
        if job is None:
            return RunOutcome("missing"), None, 0
        if job.status in TERMINAL:
            return RunOutcome(f"already_{job.status.value}"), None, 0

        # Any attempt still marked running belongs to a worker that died (we hold the lease).
        repo.close_open_attempts(
            s, job_id, AttemptStatus.LOST, error_type="WorkerLost", error="worker stopped"
        )
        if job.status == JobStatus.CANCEL_REQUESTED:
            repo.compare_and_set(
                s, job_id, [JobStatus.CANCEL_REQUESTED], JobStatus.CANCELLED, finished_at=_now()
            )
            s.commit()
            return RunOutcome("cancelled"), None, 0

        attempt_number = job.attempt_count + 1
        if attempt_number > job.max_attempts:
            last_error = s.scalar(
                select(JobAttempt.error)
                .where(JobAttempt.job_id == job_id)
                .order_by(JobAttempt.attempt_number.desc())
                .limit(1)
            )
            repo.compare_and_set(
                s,
                job_id,
                [job.status],
                JobStatus.FAILED,
                finished_at=_now(),
                error=(
                    f"poison job: gave up after {job.max_attempts} attempts"
                    f" (last error: {last_error or 'worker lost'})"
                ),
            )
            s.commit()
            return RunOutcome("failed"), None, 0

        ok = repo.compare_and_set(
            s,
            job_id,
            [JobStatus.QUEUED, JobStatus.RETRYING, JobStatus.RUNNING],
            JobStatus.RUNNING,
            attempt_count=attempt_number,
            started_at=func.coalesce(Job.started_at, func.now()),
            heartbeat_at=func.now(),
            next_retry_at=None,
        )
        if not ok:
            s.rollback()
            return RunOutcome("state_changed"), None, 0
        s.add(
            JobAttempt(
                job_id=job_id,
                attempt_number=attempt_number,
                status=AttemptStatus.RUNNING,
                worker=worker_name(),
            )
        )
        s.commit()
        return None, repo.get_job(s, job_id), attempt_number


def _checkpoint(job_id: uuid.UUID) -> Checkpoint:
    def check(stage: str, done: int, total: int) -> None:
        with get_sessionmaker()() as s:
            status = s.scalar(
                update(Job)
                .where(Job.id == job_id)
                .values(progress={"stage": stage, "done": done, "total": total})
                .returning(Job.status)
            )
            s.commit()
        if status == JobStatus.CANCEL_REQUESTED:
            raise JobCancelledError("cancelled by request")

    return check


def _record_job(task_type: str, outcome: str, started: float) -> None:
    JOBS_FINISHED.labels(task_type=task_type, outcome=outcome).inc()
    JOB_DURATION.labels(task_type=task_type).observe(time.perf_counter() - started)


def run_job(job_id: uuid.UUID, *, enqueue_retry: EnqueueRetry) -> RunOutcome:
    bind_job_id(str(job_id))
    started = time.perf_counter()
    try:
        return _run_job_inner(job_id, enqueue_retry=enqueue_retry, started=started)
    finally:
        clear_job_id()


def _run_job_inner(job_id: uuid.UUID, *, enqueue_retry: EnqueueRetry, started: float) -> RunOutcome:
    settings = get_settings()
    with job_lease(get_engine(), job_id) as acquired:
        if not acquired:
            log.info("job %s is running elsewhere; dropping duplicate delivery", job_id)
            return RunOutcome("duplicate_delivery")

        early, job, attempt_number = _start_attempt(job_id)
        if early is not None or job is None:
            return early or RunOutcome("missing")

        handler = HANDLERS.get(job.task_type)
        JOBS_STARTED.labels(task_type=job.task_type).inc()
        log.info("job %s attempt %s: %s", job_id, attempt_number, job.task_type)
        try:
            if handler is None:
                raise PermanentJobError(f"no handler for task type {job.task_type!r}")
            with Heartbeat(job_id, settings.job_heartbeat_seconds):
                outcome = handler(job, _checkpoint(job_id))
        except Exception as exc:
            return _record_failure(job, attempt_number, exc, enqueue_retry, started=started)

        with get_sessionmaker()() as s:
            done = repo.compare_and_set(
                s,
                job_id,
                [JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED],
                JobStatus.SUCCEEDED,
                finished_at=_now(),
                result_ref=outcome.result,
                error=None,
            )
            repo.close_open_attempts(s, job_id, AttemptStatus.SUCCEEDED)
            s.commit()
        if done:
            for hook in outcome.after_success:
                try:
                    hook()
                except Exception:
                    log.exception("job %s: post-success hook failed", job_id)
        _record_job(job.task_type, "succeeded", started)
        return RunOutcome("succeeded")


def _record_failure(
    job: Job, attempt_number: int, exc: Exception, enqueue_retry: EnqueueRetry, *, started: float
) -> RunOutcome:
    settings = get_settings()
    error_type, message = describe(exc)
    cancelled = isinstance(exc, JobCancelledError) or isinstance(exc.__cause__, JobCancelledError)
    with get_sessionmaker()() as s:
        status = s.scalar(select(Job.status).where(Job.id == job.id))
        if cancelled or status == JobStatus.CANCEL_REQUESTED:
            repo.close_open_attempts(s, job.id, AttemptStatus.CANCELLED, error_type="Cancelled")
            repo.compare_and_set(
                s, job.id, [JobStatus.CANCEL_REQUESTED], JobStatus.CANCELLED, finished_at=_now()
            )
            s.commit()
            log.info("job %s cancelled during attempt %s", job.id, attempt_number)
            _record_job(job.task_type, "cancelled", started)
            return RunOutcome("cancelled")

        if is_transient(exc) and attempt_number < job.max_attempts:
            delay = backoff_seconds(
                attempt_number,
                base=settings.job_retry_base_seconds,
                cap=settings.job_retry_max_seconds,
            )
            repo.close_open_attempts(
                s,
                job.id,
                AttemptStatus.FAILED,
                error_type=error_type,
                error=message,
                retry_delay_seconds=round(delay, 3),
            )
            repo.compare_and_set(
                s,
                job.id,
                [JobStatus.RUNNING],
                JobStatus.RETRYING,
                next_retry_at=_now() + timedelta(seconds=delay),
                error=message,
            )
            s.commit()
            log.warning(
                "job %s attempt %s failed (%s), retrying in %.1fs",
                job.id,
                attempt_number,
                error_type,
                delay,
            )
            enqueue_retry(job.id, job.task_type, delay, job.timeout_seconds)
            _record_job(job.task_type, "retry", started)
            return RunOutcome("retry", retry_in=delay)

        reason = (
            f"gave up after {attempt_number} attempts: {message}" if is_transient(exc) else message
        )
        repo.close_open_attempts(
            s, job.id, AttemptStatus.FAILED, error_type=error_type, error=message
        )
        repo.compare_and_set(
            s, job.id, [JobStatus.RUNNING], JobStatus.FAILED, finished_at=_now(), error=reason
        )
        s.commit()
        log.error("job %s failed permanently: %s", job.id, reason)
        _record_job(job.task_type, "failed", started)
        return RunOutcome("failed")
