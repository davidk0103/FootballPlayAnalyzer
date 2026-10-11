"""Player search, player stats, and play-by-play listings."""

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.analytics import apply_filters
from app.analytics import players as player_analytics
from app.analytics.filters import PlayFilters
from app.analytics.metrics import MetricValue, Thresholds, sample_warnings
from app.cache import AnalyticsCache, CacheStatus
from app.config import get_settings
from app.models import Player
from app.repositories import games as games_repo
from app.repositories import players as players_repo
from app.schemas import (
    GameOut,
    GamePlayOut,
    GamePlayPage,
    MetricOut,
    PlayerListItem,
    PlayerOut,
    PlayerPage,
    PlayerStatsResponse,
    SampleOut,
)
from app.services.errors import NotFoundError
from app.services.sources import public_source
from app.services.team_analytics import cache_params, filters_out


def player_out(player: Player) -> PlayerOut:
    return PlayerOut(id=player.external_player_id, name=player.name, position=player.position)


def search_players(
    session: Session,
    *,
    search: str | None,
    season: int | None,
    position: str | None,
    page: int,
    page_size: int,
) -> PlayerPage:
    rows, total = players_repo.search_players(
        session,
        search=search,
        season=season,
        position=position,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    items = [PlayerListItem(**player_out(p).model_dump(), season_plays=plays) for p, plays in rows]
    return PlayerPage(items=items, page=page, page_size=page_size, total=total)


def require_player(session: Session, player_id: str) -> Player:
    player = players_repo.get_player(session, player_id)
    if player is None:
        raise NotFoundError(f"Player '{player_id}' not found")
    return player


def _stat(value: int | MetricValue) -> int | MetricOut:
    return value if isinstance(value, int) else MetricOut(**asdict(value))


def player_stats(
    session: Session,
    player_id: str,
    filters: PlayFilters,
    *,
    cache: AnalyticsCache,
    bypass_cache: bool = False,
) -> tuple[PlayerStatsResponse, CacheStatus]:
    player = require_player(session, player_id)
    source = public_source(session, filters.season)
    thresholds = Thresholds()

    def compute() -> PlayerStatsResponse:
        frame = apply_filters(source.view(filters, None), filters)
        stats = player_analytics.player_stats(frame, player.external_player_id)
        warnings = sample_warnings(stats.plays, get_settings().min_sample_warning)
        if stats.plays == 0:
            warnings = [f"{player.name or player_id} has no plays matching these filters"]
        return PlayerStatsResponse(
            filters=filters_out(filters, thresholds),
            player=player_out(player),
            teams=stats.teams,
            sample=SampleOut(plays=stats.plays, games=stats.games),
            passing={k: _stat(v) for k, v in stats.passing.items()},
            rushing={k: _stat(v) for k, v in stats.rushing.items()},
            receiving={k: _stat(v) for k, v in stats.receiving.items()},
            definitions=player_analytics.DEFINITIONS,
            limitations=player_analytics.LIMITATIONS,
            dataset=source.dataset,
            warnings=warnings,
        )

    return cache.get_or_compute(
        namespace=f"{source.cache_scope}:player-stats",
        season=source.cache_season,
        dataset_sha=source.cache_sha,
        params=cache_params(filters, thresholds, player=player.external_player_id),
        model=PlayerStatsResponse,
        compute=compute,
        bypass=bypass_cache,
    )


def game_plays(
    session: Session, game_id: int, *, play_type: str | None, page: int, page_size: int
) -> GamePlayPage:
    game = games_repo.get_game(session, game_id)
    if game is None:
        raise NotFoundError(f"Game {game_id} not found")
    rows, total = players_repo.game_plays(
        session,
        game_id,
        play_type=play_type,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return GamePlayPage(
        game=GameOut.model_validate(game),
        items=[GamePlayOut.model_validate(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )
