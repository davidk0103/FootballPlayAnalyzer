import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.analytics.filters import Distance, FieldZone, PlayFilters, PlayType, SeasonType, Side
from app.auth.ratelimit import RateLimiter, Rule, get_rate_limiter
from app.auth.service import user_for_token
from app.cache import AnalyticsCache, get_cache
from app.config import get_settings
from app.db import get_session
from app.jobs.service import Enqueue
from app.models import ApiUsage, User
from app.services.errors import ForbiddenError, InvalidRequestError, UnauthorizedError

SessionDep = Annotated[Session, Depends(get_session)]
CacheDep = Annotated[AnalyticsCache, Depends(get_cache)]
LimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def get_enqueue() -> Enqueue:
    from app.jobs.queue import enqueue_job

    def enqueue(job_id: uuid.UUID, task_type: str, timeout_seconds: int) -> str:
        return enqueue_job(job_id, task_type, timeout_seconds=timeout_seconds)

    return enqueue


EnqueueDep = Annotated[Enqueue, Depends(get_enqueue)]


def optional_user(request: Request, session: SessionDep) -> User | None:
    return user_for_token(session, request.cookies.get(get_settings().session_cookie_name))


def session_user(request: Request, session: SessionDep) -> User:
    """Require a valid session (no usage tracking; for /auth endpoints)."""
    user = optional_user(request, session)
    if user is None:
        raise UnauthorizedError()
    return user


def current_user(request: Request, session: SessionDep) -> User:
    """Require a valid session and record the request in api_usage."""
    user = session_user(request, session)
    route = request.scope.get("route")
    endpoint = getattr(route, "path", request.url.path)
    session.add(ApiUsage(user_id=user.id, endpoint=endpoint[:200], method=request.method))
    session.commit()
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise ForbiddenError("Administrator access required", code="admin_required")
    return user


OptionalUserDep = Annotated[User | None, Depends(optional_user)]
SessionUserDep = Annotated[User, Depends(session_user)]
CurrentUserDep = Annotated[User, Depends(current_user)]
AdminDep = Annotated[User, Depends(admin_user)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(rule: Rule) -> Callable[[User, RateLimiter], None]:
    """Per-user limit for private endpoints (applied after authentication)."""

    def dependency(user: CurrentUserDep, limiter: LimiterDep) -> None:
        limiter.hit(rule, f"user:{user.id}")

    return dependency


def play_filters(
    season: Annotated[int, Query(ge=1999, le=2100, description="Season year, e.g. 2024")],
    side: Annotated[Side, Query(description="Team's plays on offense or allowed on defense")] = (
        Side.OFFENSE
    ),
    season_type: Annotated[SeasonType | None, Query(description="REG or POST")] = None,
    down: Annotated[list[int] | None, Query(description="Down(s) 1-4")] = None,
    distance: Annotated[
        Distance | None, Query(description="Yards to go: short 1-3, medium 4-7, long 8+")
    ] = None,
    field_zone: Annotated[
        FieldZone | None,
        Query(description="yardline_100: own_deep 80-99, own 50-79, opp 21-49, red_zone 1-20"),
    ] = None,
    qtr: Annotated[list[int] | None, Query(description="Quarter(s) 1-5 (5 = overtime)")] = None,
    play_type: Annotated[PlayType | None, Query(description="pass or run")] = None,
) -> PlayFilters:
    downs = tuple(sorted(set(down or [])))
    qtrs = tuple(sorted(set(qtr or [])))
    if any(d not in (1, 2, 3, 4) for d in downs):
        raise InvalidRequestError("down must be between 1 and 4")
    if any(q not in (1, 2, 3, 4, 5) for q in qtrs):
        raise InvalidRequestError("qtr must be between 1 and 5")
    return PlayFilters(
        season=season,
        side=side,
        season_type=season_type,
        down=downs,
        distance=distance,
        field_zone=field_zone,
        qtr=qtrs,
        play_type=play_type,
    )


FiltersDep = Annotated[PlayFilters, Depends(play_filters)]
