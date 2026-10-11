from typing import Any


class NotFoundError(Exception):
    """A requested resource does not exist (or is not visible to the caller). HTTP 404."""


class InvalidRequestError(Exception):
    """A request is well-formed but semantically invalid. Mapped to HTTP 422."""


class ConflictError(Exception):
    """The request conflicts with current state. Mapped to HTTP 409."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class UnauthorizedError(Exception):
    """No valid session. Mapped to HTTP 401."""

    def __init__(self, message: str = "Sign in required", code: str = "unauthorized") -> None:
        super().__init__(message)
        self.code = code


class ForbiddenError(Exception):
    """Authenticated but not allowed. Mapped to HTTP 403."""

    def __init__(self, message: str = "Not allowed", code: str = "forbidden") -> None:
        super().__init__(message)
        self.code = code


class RateLimitedError(Exception):
    """Too many requests in the current window. Mapped to HTTP 429 with Retry-After."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many requests; try again later")
        self.retry_after_seconds = retry_after_seconds


class PayloadTooLargeError(Exception):
    """Upload exceeds the configured size limit. Mapped to HTTP 413."""
