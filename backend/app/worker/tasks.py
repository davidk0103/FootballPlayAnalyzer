import logging
import uuid

from app.jobs.queue import enqueue_job
from app.jobs.reaper import reap_stale_jobs
from app.jobs.runner import run_job
from app.jobs.types import (
    EXPORT_REPORT,
    GENERATE_REPORT,
    IMPORT_SEASON,
    IMPORT_UPLOAD,
    REAP_TASK,
    TASK_NAMES,
)
from app.worker.celery_app import celery_app

log = logging.getLogger(__name__)


def _enqueue(job_id: uuid.UUID, task_type: str, countdown: float, timeout_seconds: int) -> None:
    enqueue_job(job_id, task_type, timeout_seconds=timeout_seconds, countdown=countdown)


def _run(job_id: str) -> str:
    outcome = run_job(uuid.UUID(job_id), enqueue_retry=_enqueue)
    log.info("job %s: %s", job_id, outcome.result)
    return outcome.result


@celery_app.task(name=TASK_NAMES[IMPORT_SEASON])
def run_import_job_task(job_id: str) -> str:
    return _run(job_id)


@celery_app.task(name=TASK_NAMES[IMPORT_UPLOAD])
def process_upload_task(job_id: str) -> str:
    return _run(job_id)


@celery_app.task(name=TASK_NAMES[GENERATE_REPORT])
def generate_report_task(job_id: str) -> str:
    return _run(job_id)


@celery_app.task(name=TASK_NAMES[EXPORT_REPORT])
def export_report_task(job_id: str) -> str:
    return _run(job_id)


@celery_app.task(name=REAP_TASK, acks_late=False)
def reap_stale_jobs_task() -> dict[str, list[str]]:
    report = reap_stale_jobs(_enqueue)
    return {"lost": report.lost, "requeued": report.requeued}
