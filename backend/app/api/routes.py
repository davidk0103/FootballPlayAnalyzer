import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import (
    AdminDep,
    CacheDep,
    CurrentUserDep,
    EnqueueDep,
    FiltersDep,
    OptionalUserDep,
    SessionDep,
)
from app.jobs import service as jobs
from app.jobs.state import JobStatus
from app.schemas import (
    CacheStatsOut,
    ErrorResponse,
    GameDetailOut,
    GamePage,
    HealthOut,
    ImportJobRequest,
    JobAttemptOut,
    JobOut,
    JobPage,
    ReadinessOut,
    SeasonOut,
    TeamComparisonResponse,
    TeamOut,
    TeamStatsResponse,
)
from app.services import catalog, team_analytics

ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorResponse}}
AUTH: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
}
CACHE_HEADER = "X-Cache"

NoCache = Annotated[
    bool,
    Query(description="Skip the analytics cache and compute fresh (response is not cached)"),
]

health = APIRouter(prefix="/health", tags=["health"])
api = APIRouter(prefix="/api/v1", responses=ERRORS)


@health.get("/live")
def live() -> HealthOut:
    return HealthOut(status="ok")


@health.get("/ready", responses={503: {"model": ReadinessOut}})
def ready(session: SessionDep, cache: CacheDep, response: Response) -> ReadinessOut:
    """Ready when the database answers. Redis is reported but optional (cache degrades)."""
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"
    redis_status = "ok" if cache.stats()["available"] else "unavailable"
    if database != "ok":
        response.status_code = 503
    return ReadinessOut(
        status="ok" if database == "ok" else "unavailable", database=database, redis=redis_status
    )


@api.get("/seasons", tags=["catalog"])
def list_seasons(session: SessionDep) -> list[SeasonOut]:
    return catalog.list_seasons(session)


@api.get("/teams", tags=["catalog"])
def list_teams(session: SessionDep) -> list[TeamOut]:
    return catalog.list_teams(session)


@api.get("/teams/{team_id}", tags=["catalog"])
def get_team(team_id: str, session: SessionDep) -> TeamOut:
    return catalog.get_team(session, team_id)


@api.get("/teams/{team_id}/stats", tags=["analytics"])
def team_stats(
    team_id: str,
    filters: FiltersDep,
    session: SessionDep,
    cache: CacheDep,
    response: Response,
    no_cache: NoCache = False,
) -> TeamStatsResponse:
    result, status = team_analytics.team_stats(
        session, team_id, filters, cache=cache, bypass_cache=no_cache
    )
    response.headers[CACHE_HEADER] = status.value
    return result


@api.get("/games", tags=["catalog"])
def list_games(
    session: SessionDep,
    season: Annotated[int | None, Query(ge=1999, le=2100)] = None,
    week: Annotated[int | None, Query(ge=1, le=22)] = None,
    team: Annotated[str | None, Query(description="Team abbreviation or id")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> GamePage:
    return catalog.list_games(
        session, season=season, week=week, team=team, page=page, page_size=page_size
    )


@api.get("/games/{game_id}", tags=["catalog"])
def get_game(game_id: int, session: SessionDep) -> GameDetailOut:
    return catalog.get_game(session, game_id)


@api.get("/analytics/team-comparison", tags=["analytics"])
def team_comparison(
    team_a: Annotated[str, Query(description="Team abbreviation or id")],
    team_b: Annotated[str, Query(description="Team abbreviation or id")],
    filters: FiltersDep,
    session: SessionDep,
    cache: CacheDep,
    response: Response,
    no_cache: NoCache = False,
) -> TeamComparisonResponse:
    result, status = team_analytics.compare_teams(
        session, team_a, team_b, filters, cache=cache, bypass_cache=no_cache
    )
    response.headers[CACHE_HEADER] = status.value
    return result


@api.get("/cache/stats", tags=["cache"])
def cache_stats(cache: CacheDep) -> CacheStatsOut:
    return CacheStatsOut.model_validate(cache.stats())


@api.post("/jobs/import", tags=["jobs"], status_code=202, responses={**CONFLICT, **AUTH})
def submit_import_job(
    body: ImportJobRequest,
    session: SessionDep,
    admin: AdminDep,
    enqueue: EnqueueDep,
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=200,
            description="Retries with the same key return the original job",
        ),
    ] = None,
) -> JobOut:
    submission = jobs.submit_import(
        session,
        season=body.season,
        force=body.force,
        idempotency_key=idempotency_key or body.idempotency_key,
        enqueue=enqueue,
        user=admin,
    )
    if submission.replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    return JobOut.model_validate(submission.job)


@api.get("/jobs", tags=["jobs"])
def list_jobs(
    session: SessionDep,
    viewer: OptionalUserDep,
    status: JobStatus | None = None,
    task_type: Annotated[str | None, Query(max_length=50)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> JobPage:
    """Public season imports plus, when signed in, your own private jobs."""
    items, total = jobs.list_jobs(
        session, viewer=viewer, status=status, task_type=task_type, page=page, page_size=page_size
    )
    return JobPage(
        items=[JobOut.model_validate(j) for j in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@api.get("/jobs/{job_id}", tags=["jobs"])
def get_job(job_id: uuid.UUID, session: SessionDep, viewer: OptionalUserDep) -> JobOut:
    return JobOut.model_validate(jobs.get_job(session, job_id, viewer))


@api.get("/jobs/{job_id}/attempts", tags=["jobs"])
def get_job_attempts(
    job_id: uuid.UUID, session: SessionDep, viewer: OptionalUserDep
) -> list[JobAttemptOut]:
    return [JobAttemptOut.model_validate(a) for a in jobs.list_attempts(session, job_id, viewer)]


@api.post("/jobs/{job_id}/cancel", tags=["jobs"], status_code=202, responses={**CONFLICT, **AUTH})
def cancel_job(job_id: uuid.UUID, session: SessionDep, user: CurrentUserDep) -> JobOut:
    return JobOut.model_validate(jobs.cancel_job(session, job_id, user))
