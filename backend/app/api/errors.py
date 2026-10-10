import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.errors import ConflictError, InvalidRequestError, NotFoundError

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
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    return response


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return error_response(request, 404, "not_found", str(exc))

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return error_response(request, 409, exc.code, str(exc), exc.details)

    @app.exception_handler(InvalidRequestError)
    async def invalid(request: Request, exc: InvalidRequestError) -> JSONResponse:
        return error_response(request, 422, "validation_error", str(exc))

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
