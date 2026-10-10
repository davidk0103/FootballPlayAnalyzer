"""Job error types and transient/permanent classification."""

import httpx
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import DBAPIError, OperationalError

from app.ingest.service import IngestError


class TransientJobError(RuntimeError):
    """A failure worth retrying (network blip, database restart, timeout)."""


class PermanentJobError(RuntimeError):
    """A failure that will fail the same way on retry (bad input, missing file)."""


class JobCancelledError(RuntimeError):
    """Raised at a checkpoint when the user has requested cancellation."""


def root_cause(exc: BaseException) -> BaseException:
    """Unwrap IngestError, which chains the original exception as ``__cause__``."""
    while isinstance(exc, IngestError) and exc.__cause__ is not None:
        exc = exc.__cause__
    return exc


def is_transient(exc: BaseException) -> bool:
    exc = root_cause(exc)
    if isinstance(exc, PermanentJobError):
        return False
    if isinstance(exc, TransientJobError | SoftTimeLimitExceeded | TimeoutError | ConnectionError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status == 429
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, OperationalError):
        return True
    return isinstance(exc, DBAPIError) and exc.connection_invalidated


def describe(exc: BaseException) -> tuple[str, str]:
    """(error_type, message) for storing on a job attempt."""
    root = root_cause(exc)
    if isinstance(root, SoftTimeLimitExceeded):
        return "Timeout", "job exceeded its time limit"
    return type(root).__name__, str(root)[:2000] or type(root).__name__
