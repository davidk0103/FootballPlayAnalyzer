"""Job submission, lookup, and cancellation (used by the API)."""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs import repository as repo
from app.jobs.state import JobStatus, request_fingerprint
from app.models import ImportJob, JobAttempt
from app.services.errors import ConflictError, NotFoundError

log = logging.getLogger(__name__)

IMPORT_SEASON = "import_season"
ACTIVE_TARGET_INDEX = "uq_import_jobs_active_target"

Enqueue = Callable[[uuid.UUID, int], str]


@dataclass(frozen=True)
class Submission:
    job: ImportJob
    replayed: bool


def _constraint(exc: IntegrityError) -> str | None:
    orig = exc.orig
    if isinstance(orig, UniqueViolation) and orig.diag is not None:
        return orig.diag.constraint_name
    return None


def submit_import(
    session: Session,
    *,
    season: int,
    force: bool,
    idempotency_key: str | None,
    enqueue: Enqueue,
    user_id: int | None = None,
) -> Submission:
    """Create (or replay) an import job and publish it.

    - Same idempotency key + same parameters -> the original job is returned (replay).
    - Same key + different parameters -> 409 ``idempotency_key_reused``.
    - Another active job for the same season -> 409 ``duplicate_job``.
    """
    settings = get_settings()
    params = {"season": season, "force": force}
    fingerprint = request_fingerprint(IMPORT_SEASON, params)
    key = idempotency_key or f"auto:{uuid.uuid4()}"

    existing = repo.get_by_idempotency_key(session, key)
    if existing is not None:
        return _replay(existing, fingerprint)

    job = ImportJob(
        id=uuid.uuid4(),
        user_id=user_id,
        task_type=IMPORT_SEASON,
        target_key=f"season:{season}",
        params=params,
        status=JobStatus.QUEUED,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        attempt_count=0,
        max_attempts=settings.job_max_attempts,
        timeout_seconds=settings.job_timeout_seconds,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if _constraint(exc) == ACTIVE_TARGET_INDEX:
            active = repo.get_active_for_target(session, IMPORT_SEASON, f"season:{season}")
            raise ConflictError(
                "duplicate_job",
                f"An import for season {season} is already in progress",
                {"existing_job_id": str(active.id) if active else None},
            ) from exc
        raced = repo.get_by_idempotency_key(session, key)
        if raced is not None:
            return _replay(raced, fingerprint)
        raise

    # The job row is committed before publishing. If publishing fails (Redis down) or
    # the API dies right here, the job stays QUEUED and the reaper publishes it later.
    try:
        job.celery_task_id = enqueue(job.id, job.timeout_seconds)
        session.commit()
    except Exception:
        session.rollback()
        log.warning("could not publish job %s; the reaper will retry", job.id, exc_info=True)
    return Submission(job=job, replayed=False)


def _replay(job: ImportJob, fingerprint: str) -> Submission:
    if job.request_fingerprint != fingerprint:
        raise ConflictError(
            "idempotency_key_reused",
            "This Idempotency-Key was already used with different parameters",
            {"existing_job_id": str(job.id)},
        )
    return Submission(job=job, replayed=True)


def get_job(session: Session, job_id: uuid.UUID) -> ImportJob:
    job = repo.get_job(session, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found")
    return job


def list_attempts(session: Session, job_id: uuid.UUID) -> list[JobAttempt]:
    get_job(session, job_id)
    return repo.list_attempts(session, job_id)


def cancel_job(session: Session, job_id: uuid.UUID) -> ImportJob:
    """Cancel a job. Waiting jobs stop immediately; running jobs stop at the next checkpoint."""
    now = datetime.now(UTC)
    for _ in range(3):
        job = get_job(session, job_id)
        status = job.status
        if status in (JobStatus.QUEUED, JobStatus.RETRYING):
            moved = repo.compare_and_set(
                session,
                job_id,
                [status],
                JobStatus.CANCELLED,
                cancel_requested_at=now,
                finished_at=now,
            )
        elif status == JobStatus.RUNNING:
            moved = repo.compare_and_set(
                session, job_id, [status], JobStatus.CANCEL_REQUESTED, cancel_requested_at=now
            )
        elif status == JobStatus.CANCEL_REQUESTED:
            return job
        else:
            raise ConflictError(
                "job_finished", f"Job already {status.value}", {"status": status.value}
            )
        session.commit()
        if moved:
            return get_job(session, job_id)
        # Lost a race with the worker (e.g. QUEUED -> RUNNING); re-read and try again.
    raise ConflictError("job_busy", "Job state kept changing; try again")


def list_jobs(
    session: Session, *, status: JobStatus | None, page: int, page_size: int
) -> tuple[list[ImportJob], int]:
    return repo.list_jobs(session, status=status, offset=(page - 1) * page_size, limit=page_size)
