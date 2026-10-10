from typing import Any


class NotFoundError(Exception):
    """A requested resource does not exist. Mapped to HTTP 404."""


class InvalidRequestError(Exception):
    """A request is well-formed but semantically invalid. Mapped to HTTP 422."""


class ConflictError(Exception):
    """The request conflicts with current state. Mapped to HTTP 409."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
