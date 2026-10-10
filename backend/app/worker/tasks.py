import logging
import uuid

from app.jobs.queue import enqueue_import
from app.jobs.reaper import reap_stale_jobs
from app.jobs.runner import run_import_job
from app.worker.celery_app import IMPORT_TASK, REAP_TASK, celery_app

log = logging.getLogger(__name__)


def _enqueue(job_id: uuid.UUID, countdown: float, timeout_seconds: int) -> None:
    enqueue_import(job_id, timeout_seconds=timeout_seconds, countdown=countdown)


@celery_app.task(name=IMPORT_TASK)
def run_import_job_task(job_id: str) -> str:
    outcome = run_import_job(uuid.UUID(job_id), enqueue_retry=_enqueue)
    log.info("job %s: %s", job_id, outcome.result)
    return outcome.result


@celery_app.task(name=REAP_TASK, acks_late=False)
def reap_stale_jobs_task() -> dict[str, list[str]]:
    report = reap_stale_jobs(_enqueue)
    return {"lost": report.lost, "requeued": report.requeued}
