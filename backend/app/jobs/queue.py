"""Publishing job messages to the broker."""

import uuid

from app.worker.celery_app import IMPORT_TASK, celery_app


def enqueue_import(job_id: uuid.UUID, *, timeout_seconds: int, countdown: float = 0) -> str:
    """Publish one execution message for a job and return the Celery task id.

    Publishing more than once is safe: the worker takes a per-job lease and checks the
    job's status before doing any work.
    """
    result = celery_app.send_task(
        IMPORT_TASK,
        args=[str(job_id)],
        countdown=countdown or None,
        soft_time_limit=timeout_seconds,
        time_limit=timeout_seconds + 30,
    )
    return str(result.id)
