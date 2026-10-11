"""Situational explorer, pass/run efficiency, weekly trends, and tendencies."""

from collections.abc import Callable
from dataclasses import asdict

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analytics import apply_filters
from app.analytics.filters import PlayFilters
from app.analytics.metrics import THIRD_DOWN_DEFINITION, Thresholds, definitions, sample_warnings
from app.analytics.situational import (
    GroupBy,
    efficiency_splits,
    situational_breakdown,
    weekly_trends,
)
from app.analytics.tendencies import down_distance_grid, third_down_analysis
from app.cache import AnalyticsCache, CacheStatus
from app.config import get_settings
from app.schemas import (
    EfficiencyResponse,
    EfficiencySplitOut,
    SampleOut,
    SituationalResponse,
    SituationRowOut,
    TendenciesResponse,
    TendencyCellOut,
    ThirdDownOut,
    TrendPointOut,
    TrendsResponse,
)
from app.services.sources import PlaySource
from app.services.team_analytics import cache_params, filters_out

LEAGUE_NOTE_UPLOAD = (
    "League averages and ranks are computed across the teams in your uploaded dataset."
)


def _cached[T: BaseModel](
    source: PlaySource,
    cache: AnalyticsCache,
    *,
    namespace: str,
    params: dict[str, object],
    model: type[T],
    compute: Callable[[], T],
    bypass: bool,
) -> tuple[T, CacheStatus]:
    return cache.get_or_compute(
        namespace=f"{source.cache_scope}:{namespace}",
        season=source.cache_season,
        dataset_sha=source.cache_sha,
        params=params,
        model=model,
        compute=compute,
        bypass=bypass,
    )


def _base_warnings(source: PlaySource, plays: int) -> list[str]:
    warnings = sample_warnings(plays, get_settings().min_sample_warning)
    if not source.public:
        warnings.append(LEAGUE_NOTE_UPLOAD)
    return warnings


def situational(
    session: Session,
    source: PlaySource,
    filters: PlayFilters,
    *,
    team_key: str | None,
    group_by: GroupBy,
    thresholds: Thresholds,
    cache: AnalyticsCache,
    bypass_cache: bool = False,
) -> tuple[SituationalResponse, CacheStatus]:
    team = source.require_team(session, team_key) if team_key else None

    def compute() -> SituationalResponse:
        team_plays = apply_filters(
            source.view(filters, team.abbreviation if team else None), filters
        )
        league = apply_filters(source.view(filters, None), filters) if team else None
        overall, rows = situational_breakdown(team_plays, league, group_by, thresholds)
        warnings = _base_warnings(source, overall.plays)
        small = [r.label for r in rows if 0 < r.plays < get_settings().min_sample_warning]
        if small:
            warnings.append(
                f"Small samples (under {get_settings().min_sample_warning} plays): "
                + ", ".join(small)
            )
        return SituationalResponse(
            filters=filters_out(filters, thresholds),
            team=team,
            group_by=group_by.value,
            overall=SituationRowOut.model_validate(asdict(overall)),
            rows=[SituationRowOut.model_validate(asdict(r)) for r in rows],
            definitions=definitions(thresholds),
            dataset=source.dataset,
            warnings=warnings,
        )

    return _cached(
        source,
        cache,
        namespace="situational",
        params=cache_params(
            filters, thresholds, team=team.abbreviation if team else None, group_by=group_by.value
        ),
        model=SituationalResponse,
        compute=compute,
        bypass=bypass_cache,
    )


def efficiency(
    session: Session,
    source: PlaySource,
    filters: PlayFilters,
    *,
    team_key: str,
    thresholds: Thresholds,
    cache: AnalyticsCache,
    bypass_cache: bool = False,
) -> tuple[EfficiencyResponse, CacheStatus]:
    team = source.require_team(session, team_key)

    def compute() -> EfficiencyResponse:
        team_plays = apply_filters(source.view(filters, team.abbreviation), filters)
        league = apply_filters(source.view(filters, None), filters)
        splits = efficiency_splits(team_plays, league, team.abbreviation, filters.side, thresholds)
        defs = definitions(thresholds)
        defs["rank"] = (
            "Position among all teams on EPA/play under the same filters (1 = best). "
            "Defenses are ranked by EPA/play allowed, lowest first."
        )
        defs["league"] = "Play-weighted average over every team's plays under the same filters."
        return EfficiencyResponse(
            filters=filters_out(filters, thresholds),
            team=team,
            splits=[EfficiencySplitOut.model_validate(asdict(s)) for s in splits],
            definitions=defs,
            dataset=source.dataset,
            warnings=_base_warnings(source, splits[0].plays),
        )

    return _cached(
        source,
        cache,
        namespace="efficiency",
        params=cache_params(filters, thresholds, team=team.abbreviation),
        model=EfficiencyResponse,
        compute=compute,
        bypass=bypass_cache,
    )


def trends(
    session: Session,
    source: PlaySource,
    filters: PlayFilters,
    *,
    team_key: str,
    thresholds: Thresholds,
    cache: AnalyticsCache,
    bypass_cache: bool = False,
) -> tuple[TrendsResponse, CacheStatus]:
    team = source.require_team(session, team_key)

    def compute() -> TrendsResponse:
        team_plays = apply_filters(source.view(filters, team.abbreviation), filters)
        league = apply_filters(source.view(filters, None), filters)
        points = weekly_trends(team_plays, league, thresholds)
        defs = definitions(thresholds)
        defs["league_epa_per_play"] = (
            "League-wide EPA/play in the same week under the same filters."
        )
        warnings = _base_warnings(source, sum(p.plays for p in points))
        if points and any(p.plays < 20 for p in points):
            warnings.append(
                "Some games have under 20 plays in this filter; single-game values swing a lot."
            )
        return TrendsResponse(
            filters=filters_out(filters, thresholds),
            team=team,
            games=[TrendPointOut.model_validate(asdict(p)) for p in points],
            definitions=defs,
            dataset=source.dataset,
            warnings=warnings,
        )

    return _cached(
        source,
        cache,
        namespace="trends",
        params=cache_params(filters, thresholds, team=team.abbreviation),
        model=TrendsResponse,
        compute=compute,
        bypass=bypass_cache,
    )


def tendencies(
    session: Session,
    source: PlaySource,
    filters: PlayFilters,
    *,
    team_key: str,
    cache: AnalyticsCache,
    bypass_cache: bool = False,
) -> tuple[TendenciesResponse, CacheStatus]:
    team = source.require_team(session, team_key)
    thresholds = Thresholds()

    def compute() -> TendenciesResponse:
        team_plays = apply_filters(source.view(filters, team.abbreviation), filters)
        league = apply_filters(source.view(filters, None), filters)
        grid = down_distance_grid(team_plays, league)
        third = third_down_analysis(team_plays, league, team.abbreviation, filters.side)
        plays = sum(c.plays for c in grid)
        warnings = _base_warnings(source, plays)
        if 0 < third.plays < get_settings().min_sample_warning:
            warnings.append(f"Only {third.plays} third-down plays in this sample")
        defs = {
            "pass_rate": (
                "Pass plays (including sacks) / scrimmage plays in the cell. "
                "Run rate is 1 - pass rate."
            ),
            "league_pass_rate": (
                "Pass rate of all teams in the same down and distance under the same filters."
            ),
            "third_down_conversion_rate": THIRD_DOWN_DEFINITION,
            "converted_by_penalty": (
                "Third downs converted only by an accepted defensive penalty on a play that stood."
            ),
            "avg_yards_to_go": "Mean yards to go on third-down scrimmage plays.",
            "distance": "Yards to go: short 1-3, medium 4-7, long 8+.",
            "epa_per_play": definitions()["epa_per_play"],
            "success_rate": definitions()["success_rate"],
        }
        return TendenciesResponse(
            filters=filters_out(filters, thresholds),
            team=team,
            sample=SampleOut(plays=plays, games=int(team_plays["game_key"].nunique())),
            down_distance=[TendencyCellOut.model_validate(asdict(c)) for c in grid],
            third_down=ThirdDownOut.model_validate(asdict(third)),
            definitions=defs,
            dataset=source.dataset,
            warnings=warnings,
        )

    return _cached(
        source,
        cache,
        namespace="tendencies",
        params=cache_params(filters, thresholds, team=team.abbreviation),
        model=TendenciesResponse,
        compute=compute,
        bypass=bypass_cache,
    )
