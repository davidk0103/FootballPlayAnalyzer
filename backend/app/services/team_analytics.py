"""Team stats and comparisons: fetch plays, run pure analytics, build the envelope."""

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.analytics import DEFINITIONS, PlayFilters, apply_filters, compute_team_metrics
from app.config import get_settings
from app.models import Dataset, Team
from app.repositories import plays as plays_repo
from app.schemas import (
    DatasetOut,
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
from app.services.errors import InvalidRequestError, NotFoundError

DATASET_SOURCE = "nflverse pbp"


def _require_dataset(session: Session, season: int) -> Dataset:
    dataset = plays_repo.latest_dataset(session, season)
    if dataset is None:
        raise NotFoundError(f"No imported data for season {season}")
    return dataset


def _dataset_out(dataset: Dataset) -> DatasetOut:
    return DatasetOut(source=DATASET_SOURCE, version=dataset.source_version, sha256=dataset.sha256)


def _team_stats(session: Session, team: Team, filters: PlayFilters) -> TeamStatsOut:
    plays = plays_repo.team_season_plays(session, team.id, filters.season, filters.side)
    result = compute_team_metrics(
        apply_filters(plays, filters), min_sample=get_settings().min_sample_warning
    )
    return TeamStatsOut(
        team=TeamRef.model_validate(team),
        sample=SampleOut(plays=result.plays, games=result.games),
        metrics=MetricsOut(**{name: MetricOut(**asdict(m)) for name, m in result.metrics.items()}),
        warnings=result.warnings,
    )


def team_stats(session: Session, team_key: str, filters: PlayFilters) -> TeamStatsResponse:
    team = require_team(session, team_key)
    dataset = _require_dataset(session, filters.season)
    stats = _team_stats(session, team, filters)
    return TeamStatsResponse(
        **stats.model_dump(),
        filters=FiltersOut.model_validate(filters.as_dict()),
        definitions=DEFINITIONS,
        dataset=_dataset_out(dataset),
    )


def compare_teams(
    session: Session, team_a_key: str, team_b_key: str, filters: PlayFilters
) -> TeamComparisonResponse:
    team_a = require_team(session, team_a_key)
    team_b = require_team(session, team_b_key)
    if team_a.id == team_b.id:
        raise InvalidRequestError("team_a and team_b must be different teams")
    dataset = _require_dataset(session, filters.season)
    a = _team_stats(session, team_a, filters)
    b = _team_stats(session, team_b, filters)
    warnings = [f"{s.team.abbreviation}: {w}" for s in (a, b) for w in s.warnings]
    return TeamComparisonResponse(
        filters=FiltersOut.model_validate(filters.as_dict()),
        team_a=a,
        team_b=b,
        definitions=DEFINITIONS,
        dataset=_dataset_out(dataset),
        warnings=warnings,
    )
