import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability.context import bind_request_id
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitedError,
    UnauthorizedError,
)

log = logging.getLogger(__name__)
REQUEST_ID_HEADER = "X-Request-ID"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {"code": code, "message": message, "request_id": _request_id(request)}
    }
    if details is not None:
        body["error"]["details"] = details
    headers = {REQUEST_ID_HEADER: _request_id(request) or ""}
    return JSONResponse(status_code=status, content=jsonable_encoder(body), headers=headers)


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    bind_request_id(request.state.request_id)
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    return response


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def csrf_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Require a custom header on unsafe API requests.

    Browsers cannot attach custom headers to cross-site form posts, and a cross-origin
    ``fetch`` that adds one triggers a CORS preflight that our allowlist rejects. Combined
    with the SameSite=Lax cookie this blocks CSRF without server-side token state.
    """
    if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
        from app.config import get_settings

        if request.headers.get(get_settings().csrf_header_name) != "1":
            return error_response(
                request, 403, "csrf_failed", "Missing or invalid CSRF header on unsafe request"
            )
    return await call_next(request)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return error_response(request, 404, "not_found", str(exc))

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return error_response(request, 409, exc.code, str(exc), exc.details)

    @app.exception_handler(UnauthorizedError)
    async def unauthorized(request: Request, exc: UnauthorizedError) -> JSONResponse:
        return error_response(request, 401, exc.code, str(exc))

    @app.exception_handler(ForbiddenError)
    async def forbidden(request: Request, exc: ForbiddenError) -> JSONResponse:
        return error_response(request, 403, exc.code, str(exc))

    @app.exception_handler(RateLimitedError)
    async def rate_limited(request: Request, exc: RateLimitedError) -> JSONResponse:
        resp = error_response(request, 429, "rate_limited", str(exc))
        resp.headers["Retry-After"] = str(exc.retry_after_seconds)
        return resp

    @app.exception_handler(PayloadTooLargeError)
    async def too_large(request: Request, exc: PayloadTooLargeError) -> JSONResponse:
        return error_response(request, 413, "payload_too_large", str(exc))

    @app.exception_handler(InvalidRequestError)
    async def invalid(request: Request, exc: InvalidRequestError) -> JSONResponse:
        return error_response(request, 422, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        first = details[0] if details else {"loc": [], "msg": "Invalid request"}
        where = ".".join(str(p) for p in first["loc"][1:]) or "request"
        return error_response(request, 422, "validation_error", f"{where}: {first['msg']}", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else f"http_{exc.status_code}"
        return error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error (request_id=%s)", _request_id(request))
        return error_response(request, 500, "internal_error", "Internal server error")
