"""Task-type handlers executed by the job runner.

A handler does the work for one attempt. It receives the job and a ``checkpoint``
callback that it must call regularly: the checkpoint records progress, honors
cancellation (raises JobCancelledError), and drives test fault injection. Handlers
raise exceptions for failures; the runner classifies them as transient or permanent.
Work must be idempotent: a crashed attempt is re-run from the start.
"""

from collections.abc import Callable

from app.cache import get_cache
from app.db import get_sessionmaker
from app.ingest.service import ingest_season
from app.jobs import faults
from app.jobs.handler_types import Checkpoint, Handler, HandlerResult
from app.jobs.types import IMPORT_SEASON, IMPORT_UPLOAD
from app.models import Job
from app.uploads.processing import import_upload_handler

__all__ = ["HANDLERS", "Checkpoint", "Handler", "HandlerResult"]


def import_season_handler(job: Job, checkpoint: Checkpoint) -> HandlerResult:
    season = int(job.params["season"])
    force = bool(job.params.get("force", False))
    chunks = 0

    def progress(stage: str, done: int, total: int) -> None:
        nonlocal chunks
        if done > 0:
            chunks += 1
            faults.on_chunk(season, chunks)
        checkpoint(stage, done, total)

    faults.on_attempt_start(season)
    with get_sessionmaker()() as work:
        summary = ingest_season(work, season, force=force, progress=progress)
    after: list[Callable[[], object]] = []
    if summary.status == "imported":
        after.append(lambda: get_cache().invalidate_season(season))
    return HandlerResult(summary.as_dict(), after_success=after)


HANDLERS: dict[str, Handler] = {
    IMPORT_SEASON: import_season_handler,
    IMPORT_UPLOAD: import_upload_handler,
}
