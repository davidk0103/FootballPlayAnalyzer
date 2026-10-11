"""Build a ScoutingReportOut for a saved report's parameters (used by the job)."""

import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import apply_filters
from app.analytics.filters import PlayFilters, SeasonType, Side
from app.analytics.metrics import Thresholds, definitions
from app.analytics.players import top_players
from app.analytics.report import Inputs, build_report
from app.config import get_settings
from app.models import Player, User
from app.reports.contracts import FindingOut, PlayerLeaderOut, ScoutingReportOut, SideReportOut
from app.schemas import TendencyCellOut
from app.services.sources import PlaySource, resolve_source
from app.services.team_analytics import filters_out

REPORT_DEFINITIONS = {
    "league_value": (
        "Play-weighted value over every team's plays in the same data and filters "
        "(turnovers/game: mean of per-team values)."
    ),
    "rank": "Position among teams in the data (1 = best). Shown only with 4+ teams.",
    "difference": "Team value minus league value.",
    "red_zone": "Scrimmage plays snapped at the opponent's 20 or closer.",
    "touchdown_rate": "Red-zone plays that scored an offensive touchdown / red-zone plays.",
    "findings": (
        "Rule-based: metrics ranked in the top or bottom third of teams (with at least the "
        "minimum sample), and pass rates 5+ points from league average. Not AI-generated."
    ),
}


def report_filters(params: dict[str, Any]) -> PlayFilters:
    return PlayFilters(
        season=params.get("season"),
        season_type=SeasonType(params["season_type"]) if params.get("season_type") else None,
        week_min=params.get("week_min"),
        week_max=params.get("week_max"),
        opponent=params["opponent"].upper() if params.get("opponent") else None,
    )


def _leaders(session: Session, source: PlaySource, plays: Any, team: str) -> list[PlayerLeaderOut]:
    if not source.public:
        return []
    leaders = top_players(plays, team, limit=3)
    ids = {pid for rows in leaders.values() for pid, _, _ in rows}
    players = {
        p.external_player_id: p
        for p in session.scalars(select(Player).where(Player.external_player_id.in_(ids)))
    }
    return [
        PlayerLeaderOut(
            category=category,
            player_id=pid,
            name=players[pid].name if pid in players else None,
            position=players[pid].position if pid in players else None,
            volume=volume,
            yards=yards,
        )
        for category, rows in leaders.items()
        for pid, volume, yards in rows
    ]


def generate(session: Session, params: dict[str, Any], owner: User) -> ScoutingReportOut:
    dataset_id = uuid.UUID(str(params["dataset_id"])) if params.get("dataset_id") else None
    base = report_filters(params)
    source = resolve_source(session, base.season, dataset_id, owner)
    team = source.require_team(session, str(params["team"]))
    thresholds = Thresholds(
        run_yards=int(params["explosive_run_yards"]), pass_yards=int(params["explosive_pass_yards"])
    )
    offense = replace(base, side=Side.OFFENSE)
    defense = replace(base, side=Side.DEFENSE)
    inputs = Inputs(
        team=team.abbreviation,
        offense=apply_filters(source.view(offense, team.abbreviation), offense),
        league_offense=apply_filters(source.view(offense, None), offense),
        defense=apply_filters(source.view(defense, team.abbreviation), defense),
        league_defense=apply_filters(source.view(defense, None), defense),
    )
    report = build_report(
        inputs, thresholds=thresholds, min_sample=get_settings().min_sample_warning
    )
    warnings = list(report.warnings)
    if not source.public:
        warnings.append(
            "League values and ranks are computed across the teams in your uploaded dataset."
        )
    return ScoutingReportOut(
        team=team,
        generated_at=datetime.now(UTC),
        dataset=source.dataset,
        filters=filters_out(offense, thresholds),
        offense=SideReportOut.model_validate(asdict(report.offense)),
        defense=SideReportOut.model_validate(asdict(report.defense)),
        tendencies=[TendencyCellOut.model_validate(asdict(c)) for c in report.tendencies],
        findings=[FindingOut.model_validate(asdict(f)) for f in report.findings],
        top_players=_leaders(session, source, inputs.offense, team.abbreviation),
        definitions={**definitions(thresholds), **REPORT_DEFINITIONS},
        warnings=warnings,
        limitations=report.limitations
        + (
            []
            if source.public
            else ["Player leaders are not available for uploads (no player ids)."]
        ),
    )
