class NotFoundError(Exception):
    """A requested resource does not exist. Mapped to HTTP 404."""


class InvalidRequestError(Exception):
    """A request is well-formed but semantically invalid. Mapped to HTTP 422."""
