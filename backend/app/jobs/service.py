"""Job submission, lookup, and cancellation (used by the API).

Visibility rules:
- Season imports (public task types) are visible to everyone, but only admins may
  submit or cancel them.
- Every other job is private: only its owner can see or cancel it. Other callers get
  404 rather than 403, so job ids of other users cannot be probed.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from psycopg.errors import UniqueViolation
from sqlalchemy import ColumnElement, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs import repository as repo
from app.jobs.state import JobStatus, request_fingerprint
from app.jobs.types import IMPORT_SEASON, PUBLIC_TASK_TYPES
from app.models import Job, JobAttempt, User
from app.services.errors import ConflictError, ForbiddenError, NotFoundError

log = logging.getLogger(__name__)

ACTIVE_TARGET_INDEX = "uq_jobs_active_target"

Enqueue = Callable[[uuid.UUID, str, int], str]


@dataclass(frozen=True)
class Submission:
    job: Job
    replayed: bool


def _constraint(exc: IntegrityError) -> str | None:
    orig = exc.orig
    if isinstance(orig, UniqueViolation) and orig.diag is not None:
        return orig.diag.constraint_name
    return None


def _scoped_key(user_id: int | None, key: str | None) -> str:
    """Idempotency keys are per user, so one user's key can never replay another's job."""
    if key is None:
        return f"auto:{uuid.uuid4()}"
    return f"u{user_id or 0}:{key}"


def submit_job(
    session: Session,
    *,
    task_type: str,
    target_key: str,
    params: dict[str, Any],
    user_id: int | None,
    idempotency_key: str | None,
    enqueue: Enqueue,
    duplicate_message: str,
    timeout_seconds: int | None = None,
) -> Submission:
    """Create (or replay) a job and publish it.

    - Same idempotency key + same parameters -> the original job is returned (replay).
    - Same key + different parameters -> 409 ``idempotency_key_reused``.
    - Another active job for the same (task_type, target) -> 409 ``duplicate_job``.
    """
    settings = get_settings()
    fingerprint = request_fingerprint(task_type, params)
    key = _scoped_key(user_id, idempotency_key)

    existing = repo.get_by_idempotency_key(session, key)
    if existing is not None:
        return _replay(existing, fingerprint)

    job = Job(
        id=uuid.uuid4(),
        user_id=user_id,
        task_type=task_type,
        target_key=target_key,
        params=params,
        status=JobStatus.QUEUED,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        attempt_count=0,
        max_attempts=settings.job_max_attempts,
        timeout_seconds=timeout_seconds or settings.job_timeout_seconds,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if _constraint(exc) == ACTIVE_TARGET_INDEX:
            active = repo.get_active_for_target(session, task_type, target_key)
            raise ConflictError(
                "duplicate_job",
                duplicate_message,
                {"existing_job_id": str(active.id) if active else None},
            ) from exc
        raced = repo.get_by_idempotency_key(session, key)
        if raced is not None:
            return _replay(raced, fingerprint)
        raise

    # The job row is committed before publishing. If publishing fails (Redis down) or
    # the API dies right here, the job stays QUEUED and the reaper publishes it later.
    try:
        job.celery_task_id = enqueue(job.id, task_type, job.timeout_seconds)
        session.commit()
    except Exception:
        session.rollback()
        log.warning("could not publish job %s; the reaper will retry", job.id, exc_info=True)
    return Submission(job=job, replayed=False)


def submit_import(
    session: Session,
    *,
    season: int,
    force: bool,
    idempotency_key: str | None,
    enqueue: Enqueue,
    user: User,
) -> Submission:
    if not user.is_admin:
        raise ForbiddenError("Only administrators can import seasons", code="admin_required")
    return submit_job(
        session,
        task_type=IMPORT_SEASON,
        target_key=f"season:{season}",
        params={"season": season, "force": force},
        user_id=user.id,
        idempotency_key=idempotency_key,
        enqueue=enqueue,
        duplicate_message=f"An import for season {season} is already in progress",
    )


def _replay(job: Job, fingerprint: str) -> Submission:
    if job.request_fingerprint != fingerprint:
        raise ConflictError(
            "idempotency_key_reused",
            "This Idempotency-Key was already used with different parameters",
            {"existing_job_id": str(job.id)},
        )
    return Submission(job=job, replayed=True)


def visibility(viewer: User | None) -> ColumnElement[bool]:
    public = Job.task_type.in_(list(PUBLIC_TASK_TYPES))
    if viewer is None:
        return public
    return or_(public, Job.user_id == viewer.id)


def can_view(job: Job, viewer: User | None) -> bool:
    return job.task_type in PUBLIC_TASK_TYPES or (viewer is not None and job.user_id == viewer.id)


def get_job(session: Session, job_id: uuid.UUID, viewer: User | None) -> Job:
    job = repo.get_job(session, job_id)
    if job is None or not can_view(job, viewer):
        raise NotFoundError(f"Job {job_id} not found")
    return job


def list_attempts(session: Session, job_id: uuid.UUID, viewer: User | None) -> list[JobAttempt]:
    get_job(session, job_id, viewer)
    return repo.list_attempts(session, job_id)


def _check_can_cancel(job: Job, user: User) -> None:
    if job.task_type in PUBLIC_TASK_TYPES:
        if not user.is_admin:
            raise ForbiddenError("Only administrators can cancel imports", code="admin_required")
    elif job.user_id != user.id:
        raise NotFoundError(f"Job {job.id} not found")


def cancel_job(session: Session, job_id: uuid.UUID, user: User) -> Job:
    """Cancel a job. Waiting jobs stop immediately; running jobs stop at the next checkpoint."""
    now = datetime.now(UTC)
    for _ in range(3):
        job = get_job(session, job_id, user)
        _check_can_cancel(job, user)
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
            return get_job(session, job_id, user)
        # Lost a race with the worker (e.g. QUEUED -> RUNNING); re-read and try again.
    raise ConflictError("job_busy", "Job state kept changing; try again")


def list_jobs(
    session: Session,
    *,
    viewer: User | None,
    status: JobStatus | None,
    task_type: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Job], int]:
    return repo.list_jobs(
        session,
        visible=visibility(viewer),
        status=status,
        task_type=task_type,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
