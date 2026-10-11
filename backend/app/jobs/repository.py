"""Database access for import jobs. State changes go through compare-and-set updates."""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, CursorResult, func, select, update
from sqlalchemy.orm import Session

from app.jobs.state import ACTIVE, AttemptStatus, JobStatus, check_transition
from app.models import Job, JobAttempt


def compare_and_set(
    session: Session,
    job_id: uuid.UUID,
    sources: Iterable[JobStatus],
    target: JobStatus,
    **values: Any,
) -> bool:
    """Move a job to ``target`` only if it is currently in one of ``sources``.

    Every (source, target) pair is validated against the state machine, and the
    ``WHERE status IN (...)`` clause makes concurrent writers (API cancel, worker,
    reaper) safe: exactly one of two racing updates wins.
    """
    allowed = list(sources)
    for source in allowed:
        check_transition(source, target)
    result: CursorResult[Any] = session.execute(  # type: ignore[assignment]
        update(Job)
        .where(Job.id == job_id, Job.status.in_(allowed))
        .values(status=target, updated_at=func.now(), **values)
    )
    return result.rowcount == 1


def get_job(session: Session, job_id: uuid.UUID) -> Job | None:
    return session.get(Job, job_id, populate_existing=True)


def get_by_idempotency_key(session: Session, key: str) -> Job | None:
    return session.scalar(select(Job).where(Job.idempotency_key == key))


def get_active_for_target(session: Session, task_type: str, target_key: str) -> Job | None:
    return session.scalar(
        select(Job).where(
            Job.task_type == task_type,
            Job.target_key == target_key,
            Job.status.in_(list(ACTIVE)),
        )
    )


def list_jobs(
    session: Session,
    *,
    visible: ColumnElement[bool],
    status: JobStatus | None,
    task_type: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Job], int]:
    base = select(Job).where(visible)
    if status is not None:
        base = base.where(Job.status == status)
    if task_type is not None:
        base = base.where(Job.task_type == task_type)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.scalars(
        base.order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit)
    ).all()
    return list(rows), total


def list_attempts(session: Session, job_id: uuid.UUID) -> list[JobAttempt]:
    return list(
        session.scalars(
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number)
        )
    )


def close_open_attempts(
    session: Session,
    job_id: uuid.UUID,
    status: AttemptStatus,
    *,
    error_type: str | None = None,
    error: str | None = None,
    retry_delay_seconds: float | None = None,
    now: datetime | None = None,
) -> int:
    result: CursorResult[Any] = session.execute(  # type: ignore[assignment]
        update(JobAttempt)
        .where(JobAttempt.job_id == job_id, JobAttempt.status == AttemptStatus.RUNNING)
        .values(
            status=status,
            error_type=error_type,
            error=error,
            retry_delay_seconds=retry_delay_seconds,
            finished_at=now or func.now(),
        )
    )
    return result.rowcount
