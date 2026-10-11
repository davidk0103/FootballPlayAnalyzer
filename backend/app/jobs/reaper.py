"""Recovers jobs orphaned by crashes. Runs on worker startup and periodically via beat.

- RUNNING / CANCEL_REQUESTED jobs whose heartbeat is stale *and* whose advisory-lock
  lease is free (no live process owns them) are marked lost: retried if attempts
  remain, cancelled if cancellation was pending, otherwise failed as poison.
- QUEUED / RETRYING jobs that are overdue (for example, the API committed the job but
  crashed or lost Redis before publishing the message) are re-published. Duplicate
  messages are harmless because the worker takes the lease and re-checks status.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.jobs import repository as repo
from app.jobs.locks import job_lease
from app.jobs.state import AttemptStatus, JobStatus
from app.models import Job

log = logging.getLogger(__name__)

Enqueue = Callable[[uuid.UUID, str, float, int], None]


@dataclass
class ReapReport:
    lost: list[str] = field(default_factory=list)
    requeued: list[str] = field(default_factory=list)


def reap_stale_jobs(
    enqueue: Enqueue, *, now: datetime | None = None, stale_after_seconds: float | None = None
) -> ReapReport:
    settings = get_settings()
    now = now or datetime.now(UTC)
    stale_after = stale_after_seconds or settings.job_stale_after_seconds
    stale_before = now - timedelta(seconds=stale_after)
    overdue_before = now - timedelta(seconds=settings.job_requeue_after_seconds)
    report = ReapReport()

    with get_sessionmaker()() as s:
        stale = s.scalars(
            select(Job.id).where(
                Job.status.in_([JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED]),
                func.coalesce(Job.heartbeat_at, Job.started_at, Job.created_at) < stale_before,
            )
        ).all()
    for job_id in stale:
        with job_lease(get_engine(), job_id) as acquired:
            if not acquired:
                continue  # a live worker holds it; just slow to heartbeat
            if _recover_lost(job_id, now, enqueue):
                report.lost.append(str(job_id))

    with get_sessionmaker()() as s:
        overdue = s.execute(
            select(Job.id, Job.task_type, Job.timeout_seconds).where(
                or_(
                    and_(Job.status == JobStatus.QUEUED, Job.updated_at < overdue_before),
                    and_(
                        Job.status == JobStatus.RETRYING,
                        Job.next_retry_at < overdue_before,
                    ),
                )
            )
        ).all()
        for job_id, task_type, timeout in overdue:
            s.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(updated_at=func.now(), next_retry_at=func.now())
            )
            s.commit()
            enqueue(job_id, task_type, 0, timeout)
            report.requeued.append(str(job_id))

    if report.lost or report.requeued:
        log.warning("reaper: recovered lost=%s requeued=%s", report.lost, report.requeued)
    return report


def _recover_lost(job_id: uuid.UUID, now: datetime, enqueue: Enqueue) -> bool:
    with get_sessionmaker()() as s:
        job = repo.get_job(s, job_id)
        if job is None or job.status not in (JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED):
            return False
        repo.close_open_attempts(
            s, job_id, AttemptStatus.LOST, error_type="WorkerLost", error="no heartbeat"
        )
        if job.status == JobStatus.CANCEL_REQUESTED:
            repo.compare_and_set(
                s, job_id, [JobStatus.CANCEL_REQUESTED], JobStatus.CANCELLED, finished_at=now
            )
            s.commit()
            return True
        if job.attempt_count >= job.max_attempts:
            repo.compare_and_set(
                s,
                job_id,
                [JobStatus.RUNNING],
                JobStatus.FAILED,
                finished_at=now,
                error=f"poison job: worker lost on all {job.max_attempts} attempts",
            )
            s.commit()
            return True
        moved = repo.compare_and_set(
            s, job_id, [JobStatus.RUNNING], JobStatus.RETRYING, next_retry_at=now
        )
        s.commit()
        if moved:
            enqueue(job_id, job.task_type, 0, job.timeout_seconds)
        return moved
