"""Celery application. PostgreSQL holds job state; Redis is only the message broker.

Reliability settings (see docs/decisions/005-celery-job-model.md):

- ``task_acks_late``: a message is acknowledged after the task returns, not when it is
  received, so a worker crash mid-task leaves the message to be redelivered.
- ``task_reject_on_worker_lost``: if the pool process running a task dies (OOM kill,
  SIGKILL), the message is requeued instead of being acknowledged as failed.
- ``worker_prefetch_multiplier=1``: each process reserves one message at a time, so a
  slow job does not hold others hostage and a crash affects at most one reserved task.
- ``visibility_timeout``: with the Redis transport, an unacknowledged message is
  redelivered after this long even if its worker vanished entirely.
"""

from celery import Celery
from celery.signals import worker_ready

from app.config import get_settings

IMPORT_TASK = "playbookiq.run_import_job"
REAP_TASK = "playbookiq.reap_stale_jobs"

settings = get_settings()

celery_app = Celery("playbookiq", broker=settings.broker_url, include=["app.worker.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": settings.broker_visibility_timeout_seconds},
    worker_send_task_events=False,
    beat_schedule={
        "reap-stale-jobs": {"task": REAP_TASK, "schedule": settings.reaper_interval_seconds},
    },
)


@worker_ready.connect
def _reap_on_startup(**_: object) -> None:
    """Recover jobs orphaned by a previous crash as soon as a worker comes up."""
    celery_app.send_task(REAP_TASK)
