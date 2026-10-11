"""Team stats and comparisons: load plays, run pure analytics, build the envelope."""

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.analytics import PlayFilters, apply_filters, compute_team_metrics
from app.analytics.metrics import DEFAULT_THRESHOLDS, Thresholds, definitions
from app.cache import AnalyticsCache, CacheStatus
from app.config import get_settings
from app.schemas import (
    FiltersOut,
    MetricOut,
    MetricsOut,
    SampleOut,
    TeamComparisonResponse,
    TeamRef,
    TeamStatsOut,
    TeamStatsResponse,
)
from app.services.catalog import require_team
from app.services.errors import InvalidRequestError
from app.services.sources import PlaySource, public_source


def filters_out(filters: PlayFilters, thresholds: Thresholds) -> FiltersOut:
    return FiltersOut.model_validate(
        {
            **filters.as_dict(),
            "explosive_run_yards": thresholds.run_yards,
            "explosive_pass_yards": thresholds.pass_yards,
        }
    )


def cache_params(
    filters: PlayFilters, thresholds: Thresholds, **extra: object
) -> dict[str, object]:
    return {
        **extra,
        **filters.as_dict(),
        "xr": thresholds.run_yards,
        "xp": thresholds.pass_yards,
    }


def _team_stats(
    source: PlaySource, team: TeamRef, filters: PlayFilters, thresholds: Thresholds
) -> TeamStatsOut:
    plays = apply_filters(source.view(filters, team.abbreviation), filters)
    result = compute_team_metrics(
        plays, min_sample=get_settings().min_sample_warning, thresholds=thresholds
    )
    return TeamStatsOut(
        team=team,
        sample=SampleOut(plays=result.plays, games=result.games),
        metrics=MetricsOut(**{name: MetricOut(**asdict(m)) for name, m in result.metrics.items()}),
        warnings=result.warnings,
    )


def team_stats(
    session: Session,
    team_key: str,
    filters: PlayFilters,
    *,
    cache: AnalyticsCache,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    bypass_cache: bool = False,
) -> tuple[TeamStatsResponse, CacheStatus]:
    team = TeamRef.model_validate(require_team(session, team_key))
    source = public_source(session, filters.season)

    def compute() -> TeamStatsResponse:
        stats = _team_stats(source, team, filters, thresholds)
        return TeamStatsResponse(
            **stats.model_dump(),
            filters=filters_out(filters, thresholds),
            definitions=definitions(thresholds),
            dataset=source.dataset,
        )

    return cache.get_or_compute(
        namespace="team-stats",
        season=source.cache_season,
        dataset_sha=source.cache_sha,
        params=cache_params(filters, thresholds, team=team.id),
        model=TeamStatsResponse,
        compute=compute,
        bypass=bypass_cache,
    )


def compare_teams(
    session: Session,
    team_a_key: str,
    team_b_key: str,
    filters: PlayFilters,
    *,
    cache: AnalyticsCache,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    bypass_cache: bool = False,
) -> tuple[TeamComparisonResponse, CacheStatus]:
    team_a = TeamRef.model_validate(require_team(session, team_a_key))
    team_b = TeamRef.model_validate(require_team(session, team_b_key))
    if team_a.id == team_b.id:
        raise InvalidRequestError("team_a and team_b must be different teams")
    source = public_source(session, filters.season)

    def compute() -> TeamComparisonResponse:
        a = _team_stats(source, team_a, filters, thresholds)
        b = _team_stats(source, team_b, filters, thresholds)
        warnings = [f"{s.team.abbreviation}: {w}" for s in (a, b) for w in s.warnings]
        return TeamComparisonResponse(
            filters=filters_out(filters, thresholds),
            team_a=a,
            team_b=b,
            definitions=definitions(thresholds),
            dataset=source.dataset,
            warnings=warnings,
        )

    return cache.get_or_compute(
        namespace="team-comparison",
        season=source.cache_season,
        dataset_sha=source.cache_sha,
        params=cache_params(filters, thresholds, team_a=team_a.id, team_b=team_b.id),
        model=TeamComparisonResponse,
        compute=compute,
        bypass=bypass_cache,
    )
