"""Play-calling tendencies by down and distance, and third-down analysis. Pure pandas."""

from dataclasses import dataclass

import pandas as pd

from app.analytics.filters import DISTANCE_RANGES, Distance
from app.analytics.frame import Side
from app.analytics.metrics import (
    MetricValue,
    efficiency_metrics,
    ratio,
    scrimmage_plays,
    third_down_converted,
)
from app.analytics.situational import Rank


def _distance_mask(df: pd.DataFrame, distance: Distance) -> "pd.Series[bool]":
    lo, hi = DISTANCE_RANGES[distance]
    return ((df["yards_to_go"] >= lo) & (df["yards_to_go"] <= hi)).fillna(False).astype(bool)


def _pass_rate(df: pd.DataFrame) -> MetricValue:
    return ratio(float((df["play_type"] == "pass").fillna(False).sum()), len(df))


@dataclass
class TendencyCell:
    down: int
    distance: str
    plays: int
    pass_rate: MetricValue
    epa_per_play: MetricValue
    success_rate: MetricValue
    league_pass_rate: MetricValue


def down_distance_grid(team_plays: pd.DataFrame, league_plays: pd.DataFrame) -> list[TendencyCell]:
    """Pass/run mix for every down x distance bucket (run rate = 1 - pass rate)."""
    team = scrimmage_plays(team_plays)
    league = scrimmage_plays(league_plays)
    cells = []
    for down in (1, 2, 3, 4):
        for distance in Distance:
            t = team[
                (team["down"] == down).fillna(False).astype(bool) & _distance_mask(team, distance)
            ]
            lg = league[
                (league["down"] == down).fillna(False).astype(bool)
                & _distance_mask(league, distance)
            ]
            eff = efficiency_metrics(t)
            cells.append(
                TendencyCell(
                    down=down,
                    distance=distance.value,
                    plays=len(t),
                    pass_rate=_pass_rate(t),
                    epa_per_play=eff["epa_per_play"],
                    success_rate=eff["success_rate"],
                    league_pass_rate=_pass_rate(lg),
                )
            )
    return cells


@dataclass
class ThirdDownBucket:
    distance: str
    plays: int
    conversion_rate: MetricValue
    league_conversion_rate: MetricValue
    pass_rate: MetricValue
    epa_per_play: MetricValue


@dataclass
class ThirdDownAnalysis:
    plays: int
    games: int
    conversion_rate: MetricValue
    converted_by_penalty: int
    avg_yards_to_go: float | None
    pass_rate: MetricValue
    epa_per_play: MetricValue
    league_conversion_rate: MetricValue
    rank: Rank | None
    by_distance: list[ThirdDownBucket]


def _third_downs(df: pd.DataFrame) -> pd.DataFrame:
    third = scrimmage_plays(df)
    third = third[(third["down"] == 3).fillna(False).astype(bool)]
    return third[third["third_down_converted"].notna()]


def _conversion(df: pd.DataFrame) -> MetricValue:
    return ratio(float(third_down_converted(df).sum()), len(df))


def _conversion_rank(league: pd.DataFrame, team: str, side: Side) -> Rank | None:
    values = {
        str(abbr): v
        for abbr, plays in league.groupby("team", observed=True)
        if (v := _conversion(plays).value) is not None
    }
    if team not in values:
        return None
    ordered = sorted(values.values(), reverse=side == Side.OFFENSE)
    return Rank(
        metric="third_down_conversion_rate",
        rank=ordered.index(values[team]) + 1,
        of=len(values),
        better="higher" if side == Side.OFFENSE else "lower",
    )


def third_down_analysis(
    team_plays: pd.DataFrame, league_plays: pd.DataFrame, team: str, side: Side
) -> ThirdDownAnalysis:
    t = _third_downs(team_plays)
    lg = _third_downs(league_plays)
    by_penalty = t["first_down_penalty"].astype("boolean").fillna(False) & ~t[
        "third_down_converted"
    ].astype("boolean").fillna(False)
    ytg = t["yards_to_go"].dropna()
    buckets = [
        ThirdDownBucket(
            distance=d.value,
            plays=int(_distance_mask(t, d).sum()),
            conversion_rate=_conversion(t[_distance_mask(t, d)]),
            league_conversion_rate=_conversion(lg[_distance_mask(lg, d)]),
            pass_rate=_pass_rate(t[_distance_mask(t, d)]),
            epa_per_play=efficiency_metrics(t[_distance_mask(t, d)])["epa_per_play"],
        )
        for d in Distance
    ]
    return ThirdDownAnalysis(
        plays=len(t),
        games=int(t["game_key"].nunique()),
        conversion_rate=_conversion(t),
        converted_by_penalty=int(by_penalty.sum()),
        avg_yards_to_go=round(float(ytg.mean()), 2) if len(ytg) else None,
        pass_rate=_pass_rate(t),
        epa_per_play=efficiency_metrics(t)["epa_per_play"],
        league_conversion_rate=_conversion(lg),
        rank=_conversion_rank(lg, team, side),
        by_distance=buckets,
    )
