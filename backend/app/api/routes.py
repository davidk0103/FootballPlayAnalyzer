from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import FiltersDep, SessionDep
from app.schemas import (
    ErrorResponse,
    GameDetailOut,
    GamePage,
    HealthOut,
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

health = APIRouter(prefix="/health", tags=["health"])
api = APIRouter(prefix="/api/v1", responses=ERRORS)


@health.get("/live")
def live() -> HealthOut:
    return HealthOut(status="ok")


@health.get("/ready", responses={503: {"model": HealthOut}})
def ready(session: SessionDep, response: Response) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return HealthOut(status="unavailable")
    return HealthOut(status="ok")


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
def team_stats(team_id: str, filters: FiltersDep, session: SessionDep) -> TeamStatsResponse:
    return team_analytics.team_stats(session, team_id, filters)


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
) -> TeamComparisonResponse:
    return team_analytics.compare_teams(session, team_a, team_b, filters)
