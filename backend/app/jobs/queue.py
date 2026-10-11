"""Publishing job messages to the broker."""

import uuid

from app.jobs.types import TASK_NAMES
from app.worker.celery_app import celery_app


def enqueue_job(
    job_id: uuid.UUID, task_type: str, *, timeout_seconds: int, countdown: float = 0
) -> str:
    """Publish one execution message for a job and return the Celery task id.

    Publishing more than once is safe: the worker takes a per-job lease and checks the
    job's status before doing any work.
    """
    result = celery_app.send_task(
        TASK_NAMES[task_type],
        args=[str(job_id)],
        countdown=countdown or None,
        soft_time_limit=timeout_seconds,
        time_limit=timeout_seconds + 30,
    )
    return str(result.id)
