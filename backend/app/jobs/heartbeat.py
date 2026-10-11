import logging
import threading
import uuid

from sqlalchemy import func, update

from app.db import get_sessionmaker
from app.jobs.state import JobStatus
from app.models import Job

log = logging.getLogger(__name__)


class Heartbeat:
    """Background thread that stamps ``heartbeat_at`` while a job runs.

    It dies with the worker process, so a stale heartbeat (plus a free advisory lock)
    tells the reaper the job was lost.
    """

    def __init__(self, job_id: uuid.UUID, interval: float) -> None:
        self.job_id = job_id
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{job_id}", daemon=True)

    def beat(self) -> None:
        with get_sessionmaker()() as session:
            session.execute(
                update(Job)
                .where(
                    Job.id == self.job_id,
                    Job.status.in_([JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED]),
                )
                .values(heartbeat_at=func.now())
            )
            session.commit()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.beat()
            except Exception:
                log.warning("heartbeat for job %s failed", self.job_id, exc_info=True)

    def __enter__(self) -> "Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=self.interval + 1)
