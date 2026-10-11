"""Request and job identifiers propagated through logs (never secrets or upload bodies)."""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)


def bind_request_id(request_id: str | None) -> None:
    request_id_var.set(request_id)


def bind_job_id(job_id: str | None) -> None:
    job_id_var.set(job_id)


def clear_job_id() -> None:
    job_id_var.set(None)
