"""Situational filters applied to play DataFrames. Pure pandas."""

from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd


class Side(StrEnum):
    OFFENSE = "offense"
    DEFENSE = "defense"


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


@dataclass(frozen=True)
class PlayFilters:
    season: int
    side: Side = Side.OFFENSE
    season_type: SeasonType | None = None
    down: tuple[int, ...] = field(default_factory=tuple)
    distance: Distance | None = None
    field_zone: FieldZone | None = None
    qtr: tuple[int, ...] = field(default_factory=tuple)
    play_type: PlayType | None = None

    def as_dict(self) -> dict[str, object]:
        """Only the filters that were set, for echoing back in responses."""
        out: dict[str, object] = {"season": self.season, "side": self.side.value}
        if self.season_type:
            out["season_type"] = self.season_type.value
        if self.down:
            out["down"] = list(self.down)
        if self.distance:
            out["distance"] = self.distance.value
        if self.field_zone:
            out["field_zone"] = self.field_zone.value
        if self.qtr:
            out["qtr"] = list(self.qtr)
        if self.play_type:
            out["play_type"] = self.play_type.value
        return out


def _between(series: "pd.Series[float]", bounds: tuple[int, int]) -> "pd.Series[bool]":
    lo, hi = bounds
    return series.notna() & (series >= lo) & (series <= hi)


def apply_filters(df: pd.DataFrame, filters: PlayFilters) -> pd.DataFrame:
    """Apply situational filters (season and side are handled by the caller's query)."""
    mask = pd.Series(True, index=df.index)
    if filters.season_type:
        mask &= df["season_type"] == filters.season_type.value
    if filters.down:
        mask &= df["down"].isin(filters.down)
    if filters.distance:
        mask &= _between(df["yards_to_go"], DISTANCE_RANGES[filters.distance])
    if filters.field_zone:
        mask &= _between(df["yard_line_100"], FIELD_ZONE_RANGES[filters.field_zone])
    if filters.qtr:
        mask &= df["qtr"].isin(filters.qtr)
    if filters.play_type:
        mask &= df["play_type"] == filters.play_type.value
    return df[mask]
