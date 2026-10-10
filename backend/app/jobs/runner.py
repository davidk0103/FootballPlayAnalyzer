"""Executes one delivery of an import job. Called by the Celery task.

Delivery is at-least-once, so this function must be safe to run any number of times
for the same job:

1. Take the job's advisory-lock lease; if another process holds it, this is a
   duplicate delivery and we drop it.
2. Re-read the job. Terminal jobs are left alone; a pending cancellation is honored.
3. Count the attempt (exhausted attempts = poison job -> FAILED), record it, and run
   the shared ingestion service in one transaction with heartbeat + cancel checkpoints.
4. Record the outcome with compare-and-set updates, schedule a retry with backoff for
   transient errors, and invalidate the analytics cache after a successful import.
"""

import logging
import os
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.cache import get_cache
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.ingest.service import ingest_season
from app.jobs import faults
from app.jobs import repository as repo
from app.jobs.errors import JobCancelledError, describe, is_transient
from app.jobs.heartbeat import Heartbeat
from app.jobs.locks import job_lease
from app.jobs.state import TERMINAL, AttemptStatus, JobStatus, backoff_seconds
from app.models import ImportJob, JobAttempt

log = logging.getLogger(__name__)

EnqueueRetry = Callable[[uuid.UUID, float, int], None]


@dataclass(frozen=True)
class RunOutcome:
    result: str
    retry_in: float | None = None


def worker_name() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _now() -> datetime:
    return datetime.now(UTC)


def _start_attempt(job_id: uuid.UUID) -> tuple[RunOutcome | None, ImportJob | None, int]:
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
            started_at=func.coalesce(ImportJob.started_at, func.now()),
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


def _checkpoint(job_id: uuid.UUID, season: int) -> Callable[[str, int, int], None]:
    chunks = 0

    def check(stage: str, done: int, total: int) -> None:
        nonlocal chunks
        if done > 0:
            chunks += 1
            faults.on_chunk(season, chunks)
        with get_sessionmaker()() as s:
            status = s.scalar(select(ImportJob.status).where(ImportJob.id == job_id))
        if status == JobStatus.CANCEL_REQUESTED:
            raise JobCancelledError("cancelled by request")

    return check


def run_import_job(job_id: uuid.UUID, *, enqueue_retry: EnqueueRetry) -> RunOutcome:
    settings = get_settings()
    with job_lease(get_engine(), job_id) as acquired:
        if not acquired:
            log.info("job %s is running elsewhere; dropping duplicate delivery", job_id)
            return RunOutcome("duplicate_delivery")

        early, job, attempt_number = _start_attempt(job_id)
        if early is not None or job is None:
            return early or RunOutcome("missing")

        season = int(job.params["season"])
        force = bool(job.params.get("force", False))
        log.info("job %s attempt %s: importing season %s", job_id, attempt_number, season)
        try:
            with Heartbeat(job_id, settings.job_heartbeat_seconds):
                faults.on_attempt_start(season)
                with get_sessionmaker()() as work:
                    summary = ingest_season(
                        work, season, force=force, progress=_checkpoint(job_id, season)
                    )
        except Exception as exc:
            return _record_failure(job, attempt_number, exc, enqueue_retry)

        with get_sessionmaker()() as s:
            done = repo.compare_and_set(
                s,
                job_id,
                [JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED],
                JobStatus.SUCCEEDED,
                finished_at=_now(),
                result_ref=summary.as_dict(),
                error=None,
            )
            repo.close_open_attempts(s, job_id, AttemptStatus.SUCCEEDED)
            s.commit()
        if done and summary.status == "imported":
            get_cache().invalidate_season(season)
        return RunOutcome("succeeded")


def _record_failure(
    job: ImportJob, attempt_number: int, exc: Exception, enqueue_retry: EnqueueRetry
) -> RunOutcome:
    settings = get_settings()
    error_type, message = describe(exc)
    cancelled = isinstance(exc, JobCancelledError) or isinstance(exc.__cause__, JobCancelledError)
    with get_sessionmaker()() as s:
        status = s.scalar(select(ImportJob.status).where(ImportJob.id == job.id))
        if cancelled or status == JobStatus.CANCEL_REQUESTED:
            repo.close_open_attempts(s, job.id, AttemptStatus.CANCELLED, error_type="Cancelled")
            repo.compare_and_set(
                s, job.id, [JobStatus.CANCEL_REQUESTED], JobStatus.CANCELLED, finished_at=_now()
            )
            s.commit()
            log.info("job %s cancelled during attempt %s", job.id, attempt_number)
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
            enqueue_retry(job.id, delay, job.timeout_seconds)
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
        return RunOutcome("failed")
