"""M3 analytics: situational explorer, efficiency, trends, tendencies, players, plays."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.analytics.situational import GroupBy
from app.api.deps import CacheDep, FiltersDep, SessionDep, ThresholdsDep
from app.api.routes import CACHE_HEADER, ERRORS, NoCache
from app.schemas import (
    EfficiencyResponse,
    GamePlayPage,
    PlayerOut,
    PlayerPage,
    PlayerStatsResponse,
    SituationalResponse,
    TendenciesResponse,
    TrendsResponse,
)
from app.services import players, situational
from app.services.sources import public_source

router = APIRouter(prefix="/api/v1", responses=ERRORS)

TeamQuery = Annotated[str, Query(description="Team abbreviation (or id for public data)")]


@router.get("/analytics/situational", tags=["analytics"])
def situational_explorer(
    filters: FiltersDep,
    thresholds: ThresholdsDep,
    session: SessionDep,
    cache: CacheDep,
    response: Response,
    group_by: Annotated[GroupBy, Query(description="Dimension to split plays by")] = (GroupBy.DOWN),
    team: Annotated[
        str | None, Query(description="Team abbreviation; omit for the whole league")
    ] = None,
    no_cache: NoCache = False,
) -> SituationalResponse:
    """Metrics per situation bucket, with the league average in the same bucket."""
    source = public_source(session, filters.season)
    result, status = situational.situational(
        session,
        source,
        filters,
        team_key=team,
        group_by=group_by,
        thresholds=thresholds,
        cache=cache,
        bypass_cache=no_cache,
    )
    response.headers[CACHE_HEADER] = status.value
    return result


@router.get("/analytics/efficiency", tags=["analytics"])
def efficiency(
    team: TeamQuery,
    filters: FiltersDep,
    thresholds: ThresholdsDep,
    session: SessionDep,
    cache: CacheDep,
    response: Response,
    no_cache: NoCache = False,
) -> EfficiencyResponse:
    """Passing vs rushing efficiency with league averages and the team's EPA rank."""
    source = public_source(session, filters.season)
    result, status = situational.efficiency(
        session,
        source,
        filters,
        team_key=team,
        thresholds=thresholds,
        cache=cache,
        bypass_cache=no_cache,
    )
    response.headers[CACHE_HEADER] = status.value
    return result


@router.get("/analytics/trends", tags=["analytics"])
def trends(
    team: TeamQuery,
    filters: FiltersDep,
    thresholds: ThresholdsDep,
    session: SessionDep,
    cache: CacheDep,
    response: Response,
    no_cache: NoCache = False,
) -> TrendsResponse:
    """Per-game metrics in schedule order, with that week's league EPA/play."""
    source = public_source(session, filters.season)
    result, status = situational.trends(
        session,
        source,
        filters,
        team_key=team,
        thresholds=thresholds,
        cache=cache,
        bypass_cache=no_cache,
    )
    response.headers[CACHE_HEADER] = status.value
    return result


@router.get("/teams/{team_id}/tendencies", tags=["analytics"])
def team_tendencies(
    team_id: str,
    filters: FiltersDep,
    session: SessionDep,
    cache: CacheDep,
    response: Response,
    no_cache: NoCache = False,
) -> TendenciesResponse:
    """Pass/run frequency by down and distance, plus a third-down breakdown."""
    source = public_source(session, filters.season)
    result, status = situational.tendencies(
        session, source, filters, team_key=team_id, cache=cache, bypass_cache=no_cache
    )
    response.headers[CACHE_HEADER] = status.value
    return result


@router.get("/players", tags=["players"])
def list_players(
    session: SessionDep,
    search: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
    season: Annotated[
        int | None, Query(ge=1999, le=2100, description="Only players involved in this season")
    ] = None,
    position: Annotated[str | None, Query(max_length=5, description="e.g. QB, RB, WR")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PlayerPage:
    return players.search_players(
        session,
        search=search,
        season=season,
        position=position,
        page=page,
        page_size=page_size,
    )


@router.get("/players/{player_id}", tags=["players"])
def get_player(player_id: str, session: SessionDep) -> PlayerOut:
    return players.player_out(players.require_player(session, player_id))


@router.get("/players/{player_id}/stats", tags=["players"])
def player_stats(
    player_id: str,
    filters: FiltersDep,
    session: SessionDep,
    cache: CacheDep,
    response: Response,
    no_cache: NoCache = False,
) -> PlayerStatsResponse:
    """Passing, rushing, and receiving stats from official-stat yardage columns."""
    result, status = players.player_stats(
        session, player_id, filters, cache=cache, bypass_cache=no_cache
    )
    response.headers[CACHE_HEADER] = status.value
    return result


@router.get("/games/{game_id}/plays", tags=["catalog"])
def game_plays(
    game_id: int,
    session: SessionDep,
    play_type: Annotated[
        str | None, Query(max_length=20, description="e.g. pass, run, punt")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> GamePlayPage:
    return players.game_plays(session, game_id, play_type=play_type, page=page, page_size=page_size)
