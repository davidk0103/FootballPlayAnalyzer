"""Situational filters applied to play frames. Pure pandas.

Filters run on a ``team_view`` frame (see ``frame.py``), which carries ``opponent``
and ``team_score_diff`` from the selected team's perspective.
"""

from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

from app.analytics.frame import Side

__all__ = [
    "DISTANCE_RANGES",
    "FIELD_ZONE_RANGES",
    "SCORE_STATE_RANGES",
    "Distance",
    "FieldZone",
    "PlayFilters",
    "PlayType",
    "ScoreState",
    "SeasonType",
    "Side",
    "apply_filters",
]


class Distance(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class FieldZone(StrEnum):
    OWN_DEEP = "own_deep"
    OWN = "own"
    OPP = "opp"
    RED_ZONE = "red_zone"


class PlayType(StrEnum):
    PASS = "pass"
    RUN = "run"


class SeasonType(StrEnum):
    REG = "REG"
    POST = "POST"


class ScoreState(StrEnum):
    """Score margin from the selected team's perspective (one score = up to 8 points)."""

    TRAILING_BIG = "trailing_9plus"
    TRAILING = "trailing_1_8"
    TIED = "tied"
    LEADING = "leading_1_8"
    LEADING_BIG = "leading_9plus"


# Inclusive (min, max) yards to go.
DISTANCE_RANGES: dict[Distance, tuple[int, int]] = {
    Distance.SHORT: (1, 3),
    Distance.MEDIUM: (4, 7),
    Distance.LONG: (8, 99),
}
# Inclusive (min, max) yardline_100 (yards from the opponent's end zone).
FIELD_ZONE_RANGES: dict[FieldZone, tuple[int, int]] = {
    FieldZone.OWN_DEEP: (80, 99),
    FieldZone.OWN: (50, 79),
    FieldZone.OPP: (21, 49),
    FieldZone.RED_ZONE: (1, 20),
}
# Inclusive (min, max) team score differential.
SCORE_STATE_RANGES: dict[ScoreState, tuple[int, int]] = {
    ScoreState.TRAILING_BIG: (-200, -9),
    ScoreState.TRAILING: (-8, -1),
    ScoreState.TIED: (0, 0),
    ScoreState.LEADING: (1, 8),
    ScoreState.LEADING_BIG: (9, 200),
}


@dataclass(frozen=True)
class PlayFilters:
    # None only for uploaded datasets without a season column.
    season: int | None
    side: Side = Side.OFFENSE
    season_type: SeasonType | None = None
    week_min: int | None = None
    week_max: int | None = None
    opponent: str | None = None
    down: tuple[int, ...] = field(default_factory=tuple)
    distance: Distance | None = None
    field_zone: FieldZone | None = None
    qtr: tuple[int, ...] = field(default_factory=tuple)
    score_state: ScoreState | None = None
    play_type: PlayType | None = None

    def as_dict(self) -> dict[str, object]:
        """Only the filters that were set, for echoing back in responses and cache keys."""
        out: dict[str, object] = {"season": self.season, "side": self.side.value}
        if self.season_type:
            out["season_type"] = self.season_type.value
        if self.week_min is not None:
            out["week_min"] = self.week_min
        if self.week_max is not None:
            out["week_max"] = self.week_max
        if self.opponent:
            out["opponent"] = self.opponent
        if self.down:
            out["down"] = list(self.down)
        if self.distance:
            out["distance"] = self.distance.value
        if self.field_zone:
            out["field_zone"] = self.field_zone.value
        if self.qtr:
            out["qtr"] = list(self.qtr)
        if self.score_state:
            out["score_state"] = self.score_state.value
        if self.play_type:
            out["play_type"] = self.play_type.value
        return out


def _between(series: "pd.Series[float]", bounds: tuple[int, int]) -> "pd.Series[bool]":
    lo, hi = bounds
    return (series.notna() & (series >= lo) & (series <= hi)).fillna(False).astype(bool)


def apply_filters(df: pd.DataFrame, filters: PlayFilters) -> pd.DataFrame:
    """Apply situational filters to a team_view frame.

    Season and team/side selection happen when the frame is loaded. Rows whose value
    for a filtered column is unknown are excluded (never guessed into a bucket).
    """
    mask = pd.Series(True, index=df.index)
    if filters.season_type:
        mask &= (df["season_type"] == filters.season_type.value).fillna(False)
    if filters.week_min is not None:
        mask &= (df["week"] >= filters.week_min).fillna(False)
    if filters.week_max is not None:
        mask &= (df["week"] <= filters.week_max).fillna(False)
    if filters.opponent:
        mask &= (df["opponent"] == filters.opponent).fillna(False)
    if filters.down:
        mask &= df["down"].isin(filters.down).fillna(False)
    if filters.distance:
        mask &= _between(df["yards_to_go"], DISTANCE_RANGES[filters.distance])
    if filters.field_zone:
        mask &= _between(df["yard_line_100"], FIELD_ZONE_RANGES[filters.field_zone])
    if filters.qtr:
        mask &= df["qtr"].isin(filters.qtr).fillna(False)
    if filters.score_state:
        mask &= _between(df["team_score_diff"], SCORE_STATE_RANGES[filters.score_state])
    if filters.play_type:
        mask &= (df["play_type"] == filters.play_type.value).fillna(False)
    return df[mask.astype(bool)]
