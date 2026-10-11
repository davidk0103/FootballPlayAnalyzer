"""Situational splits, pass/run efficiency with league context, and weekly trends.

Every function takes already loaded frames and returns plain data; no I/O.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from app.analytics.filters import (
    DISTANCE_RANGES,
    FIELD_ZONE_RANGES,
    SCORE_STATE_RANGES,
    Distance,
    FieldZone,
    ScoreState,
)
from app.analytics.frame import Side
from app.analytics.metrics import (
    DEFAULT_THRESHOLDS,
    MetricValue,
    Thresholds,
    efficiency_metrics,
    explosive_metrics,
    scrimmage_plays,
    situation_metrics,
)


class GroupBy(StrEnum):
    DOWN = "down"
    DISTANCE = "distance"
    FIELD_ZONE = "field_zone"
    QUARTER = "qtr"
    SCORE_STATE = "score_state"
    PLAY_TYPE = "play_type"


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    mask: Callable[[pd.DataFrame], "pd.Series[bool]"]


def _in_range(col: str, lo: int, hi: int) -> Callable[[pd.DataFrame], "pd.Series[bool]"]:
    return lambda df: ((df[col] >= lo) & (df[col] <= hi)).fillna(False).astype(bool)


def _equals(col: str, value: object) -> Callable[[pd.DataFrame], "pd.Series[bool]"]:
    return lambda df: (df[col] == value).fillna(False).astype(bool)


DISTANCE_LABELS = {
    Distance.SHORT: "Short (1-3)",
    Distance.MEDIUM: "Medium (4-7)",
    Distance.LONG: "Long (8+)",
}
FIELD_ZONE_LABELS = {
    FieldZone.OWN_DEEP: "Own 1-20",
    FieldZone.OWN: "Own 21-50",
    FieldZone.OPP: "Opponent 49-21",
    FieldZone.RED_ZONE: "Red zone",
}
SCORE_STATE_LABELS = {
    ScoreState.TRAILING_BIG: "Trailing by 9+",
    ScoreState.TRAILING: "Trailing by 1-8",
    ScoreState.TIED: "Tied",
    ScoreState.LEADING: "Leading by 1-8",
    ScoreState.LEADING_BIG: "Leading by 9+",
}

GROUPS: dict[GroupBy, list[Group]] = {
    GroupBy.DOWN: [
        Group(str(d), label, _equals("down", d))
        for d, label in ((1, "1st down"), (2, "2nd down"), (3, "3rd down"), (4, "4th down"))
    ],
    GroupBy.DISTANCE: [
        Group(d.value, DISTANCE_LABELS[d], _in_range("yards_to_go", *DISTANCE_RANGES[d]))
        for d in Distance
    ],
    GroupBy.FIELD_ZONE: [
        Group(z.value, FIELD_ZONE_LABELS[z], _in_range("yard_line_100", *FIELD_ZONE_RANGES[z]))
        for z in FieldZone
    ],
    GroupBy.QUARTER: [
        Group(str(q), label, _equals("qtr", q))
        for q, label in ((1, "Q1"), (2, "Q2"), (3, "Q3"), (4, "Q4"), (5, "Overtime"))
    ],
    GroupBy.SCORE_STATE: [
        Group(s.value, SCORE_STATE_LABELS[s], _in_range("team_score_diff", *SCORE_STATE_RANGES[s]))
        for s in ScoreState
    ],
    GroupBy.PLAY_TYPE: [
        Group("pass", "Pass (incl. sacks)", _equals("play_type", "pass")),
        Group("run", "Run (incl. scrambles)", _equals("play_type", "run")),
    ],
}


@dataclass
class SituationRow:
    key: str
    label: str
    plays: int
    games: int
    metrics: dict[str, MetricValue]
    league: dict[str, MetricValue] | None


def situational_breakdown(
    team_plays: pd.DataFrame,
    league_plays: pd.DataFrame | None,
    group_by: GroupBy,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> tuple[SituationRow, list[SituationRow]]:
    """Split filtered plays into situation buckets; league values use the same buckets.

    ``team_plays`` / ``league_plays`` must already be filtered team_view frames. Pass
    ``league_plays=None`` when the subject already is the whole league.
    """
    team = scrimmage_plays(team_plays)
    league = scrimmage_plays(league_plays) if league_plays is not None else None

    def row(key: str, label: str, plays: pd.DataFrame, lg: pd.DataFrame | None) -> SituationRow:
        return SituationRow(
            key=key,
            label=label,
            plays=len(plays),
            games=int(plays["game_key"].nunique()),
            metrics=situation_metrics(plays, thresholds),
            league=situation_metrics(lg, thresholds) if lg is not None else None,
        )

    overall = row("all", "All situations", team, league)
    rows = [
        row(
            g.key,
            g.label,
            team[g.mask(team)],
            league[g.mask(league)] if league is not None else None,
        )
        for g in GROUPS[group_by]
    ]
    return overall, rows


@dataclass
class Rank:
    metric: str
    rank: int
    of: int
    better: str


def rank_teams(
    league_plays: pd.DataFrame, team: str, side: Side, metric: str = "epa_per_play"
) -> Rank | None:
    """Rank ``team`` among all teams on ``metric`` (1 = best).

    Offenses rank high-to-low; defenses rank low-to-high, because a defense wants to
    allow less. ``league_plays`` is a filtered league-wide team_view for ``side``.
    """
    values: dict[str, float] = {}
    for abbr, plays in league_plays.groupby("team", observed=True):
        value = efficiency_metrics(plays)[metric].value
        if value is not None:
            values[str(abbr)] = value
    if team not in values:
        return None
    ordered = sorted(values.values(), reverse=side == Side.OFFENSE)
    return Rank(
        metric=metric,
        rank=ordered.index(values[team]) + 1,
        of=len(values),
        better="higher" if side == Side.OFFENSE else "lower",
    )


@dataclass
class EfficiencySplit:
    key: str
    label: str
    plays: int
    games: int
    metrics: dict[str, MetricValue]
    league: dict[str, MetricValue]
    rank: Rank | None


SPLITS = (("all", "All plays", None), ("pass", "Passing", "pass"), ("run", "Rushing", "run"))


def efficiency_splits(
    team_plays: pd.DataFrame,
    league_plays: pd.DataFrame,
    team: str,
    side: Side,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> list[EfficiencySplit]:
    """Pass vs run efficiency for one team, with the league average and the team's rank."""
    team_s = scrimmage_plays(team_plays)
    league_s = scrimmage_plays(league_plays)
    out = []
    for key, label, play_type in SPLITS:
        t = (
            team_s
            if play_type is None
            else team_s[(team_s["play_type"] == play_type).fillna(False)]
        )
        lg = (
            league_s
            if play_type is None
            else league_s[(league_s["play_type"] == play_type).fillna(False)]
        )

        def metrics(df: pd.DataFrame, split: str | None = play_type) -> dict[str, MetricValue]:
            m = {**efficiency_metrics(df), **explosive_metrics(df, thresholds)}
            if split is not None:
                m.pop("pass_rate")
            return m

        out.append(
            EfficiencySplit(
                key=key,
                label=label,
                plays=len(t),
                games=int(t["game_key"].nunique()),
                metrics=metrics(t),
                league=metrics(lg),
                rank=rank_teams(lg, team, side),
            )
        )
    return out


@dataclass
class TrendPoint:
    game_key: str
    week: int | None
    season_type: str | None
    opponent: str | None
    plays: int
    metrics: dict[str, MetricValue]
    league_epa_per_play: float | None


def weekly_trends(
    team_plays: pd.DataFrame,
    league_plays: pd.DataFrame,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> list[TrendPoint]:
    """One point per game, in schedule order, with that week's league-wide EPA/play."""
    team = scrimmage_plays(team_plays)
    league = scrimmage_plays(league_plays)
    league_by_week: dict[tuple[object, object], float | None] = {
        (wk, st): efficiency_metrics(df)["epa_per_play"].value
        for (wk, st), df in league.groupby(["week", "season_type"], observed=True, dropna=False)
    }
    points = []
    for game_key, plays in team.groupby("game_key", observed=True, sort=False):
        week = plays["week"].dropna()
        season_type = plays["season_type"].dropna()
        opponent = plays["opponent"].dropna()
        wk = int(week.iloc[0]) if len(week) else None
        st = str(season_type.iloc[0]) if len(season_type) else None
        points.append(
            TrendPoint(
                game_key=str(game_key),
                week=wk,
                season_type=st,
                opponent=str(opponent.mode().iloc[0]) if len(opponent) else None,
                plays=len(plays),
                metrics=situation_metrics(plays, thresholds),
                league_epa_per_play=league_by_week.get((wk, st)),
            )
        )
    order = {"REG": 0, "POST": 1}
    points.sort(key=lambda p: (order.get(p.season_type or "", 2), p.week or 0, p.game_key))
    return points
