from typing import Any

from fastapi import APIRouter, Request, Response

from app.api.deps import LimiterDep, SessionDep, SessionUserDep, client_ip
from app.auth import ratelimit
from app.auth import service as auth
from app.auth.tokens import issue_token
from app.config import get_settings
from app.models import User
from app.schemas import CredentialsIn, ErrorResponse, UserOut

AUTH_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/auth", tags=["auth"], responses=AUTH_ERRORS)


def _set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        issue_token(user.id, user.token_version),
        max_age=int(settings.jwt_ttl_hours * 3600),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


@router.post("/register", status_code=201)
def register(
    body: CredentialsIn,
    request: Request,
    response: Response,
    session: SessionDep,
    limiter: LimiterDep,
) -> UserOut:
    limiter.hit(ratelimit.REGISTER_IP, client_ip(request))
    user = auth.register(session, email=body.email, password=body.password)
    _set_session_cookie(response, user)
    return UserOut.model_validate(user)


@router.post("/login")
def login(
    body: CredentialsIn,
    request: Request,
    response: Response,
    session: SessionDep,
    limiter: LimiterDep,
) -> UserOut:
    limiter.hit(ratelimit.LOGIN_IP, client_ip(request))
    limiter.hit(ratelimit.LOGIN_EMAIL, body.email.strip().lower())
    user = auth.authenticate(session, email=body.email, password=body.password)
    _set_session_cookie(response, user)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    _clear_session_cookie(response)


@router.post("/logout-all", status_code=204)
def logout_all(user: SessionUserDep, session: SessionDep, response: Response) -> None:
    """Revoke every session for this user (all devices), including the current one."""
    auth.revoke_all_sessions(session, user)
    _clear_session_cookie(response)


@router.get("/me")
def me(user: SessionUserDep) -> UserOut:
    return UserOut.model_validate(user)
