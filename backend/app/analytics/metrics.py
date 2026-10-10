"""Team metrics computed from play DataFrames. Pure pandas, no database or HTTP.

Expected columns: game_id, play_type, down, yards_gained, epa, success,
interception, fumble_lost, third_down_converted, two_point_attempt, play_deleted.
"""

from dataclasses import dataclass, field

import pandas as pd

SCRIMMAGE_PLAY_TYPES = ("pass", "run")
EXPLOSIVE_RUN_YARDS = 10
EXPLOSIVE_PASS_YARDS = 20

DEFINITIONS: dict[str, str] = {
    "epa_per_play": (
        "Sum of expected points added / scrimmage plays with EPA. Scrimmage plays are "
        "passes (incl. sacks) and runs (incl. scrambles), excluding penalties that "
        "nullified the play, kneels, spikes, and two-point tries."
    ),
    "success_rate": (
        "Share of scrimmage plays with positive EPA (the nflverse definition of success, "
        "not the 40/60/100% down-based rule)."
    ),
    "yards_per_play": "Total yards gained / scrimmage plays.",
    "pass_rate": "Pass plays (including sacks) / scrimmage plays.",
    "third_down_conversion_rate": (
        "Third-down scrimmage plays that gained a first down (including by defensive "
        "penalty on a play that stood) / third-down scrimmage plays."
    ),
    "explosive_play_rate": (
        f"Runs of {EXPLOSIVE_RUN_YARDS}+ yards or passes of {EXPLOSIVE_PASS_YARDS}+ yards "
        "/ scrimmage plays."
    ),
    "turnovers_per_game": "(Interceptions + fumbles lost) / games in the sample.",
}


@dataclass(frozen=True)
class MetricValue:
    value: float | None
    numerator: float
    denominator: int


@dataclass
class TeamMetrics:
    plays: int
    games: int
    metrics: dict[str, MetricValue]
    warnings: list[str] = field(default_factory=list)


def ratio(numerator: float, denominator: int, digits: int = 4) -> MetricValue:
    """A metric value; ``None`` (never 0) when the denominator is zero."""
    value = None if denominator == 0 else round(numerator / denominator, digits)
    return MetricValue(
        value=value, numerator=round(float(numerator), digits), denominator=denominator
    )


def _true(series: "pd.Series[bool]") -> "pd.Series[bool]":
    return series.astype("boolean").fillna(False).astype(bool)


def scrimmage_plays(df: pd.DataFrame) -> pd.DataFrame:
    mask = (
        df["play_type"].isin(SCRIMMAGE_PLAY_TYPES)
        & ~_true(df["two_point_attempt"])
        & ~_true(df["play_deleted"])
    )
    return df[mask]


def efficiency_metrics(plays: pd.DataFrame) -> dict[str, MetricValue]:
    with_epa = plays["epa"].dropna()
    with_success = plays["success"].dropna()
    with_yards = plays["yards_gained"].dropna()
    return {
        "epa_per_play": ratio(float(with_epa.sum()), len(with_epa)),
        "success_rate": ratio(float(_true(with_success).sum()), len(with_success)),
        "yards_per_play": ratio(float(with_yards.sum()), len(with_yards)),
        "pass_rate": ratio(float((plays["play_type"] == "pass").sum()), len(plays)),
    }


def third_down_metrics(plays: pd.DataFrame) -> dict[str, MetricValue]:
    third = plays[plays["down"] == 3]["third_down_converted"].dropna()
    return {"third_down_conversion_rate": ratio(float(_true(third).sum()), len(third))}


def explosive_metrics(plays: pd.DataFrame) -> dict[str, MetricValue]:
    known = plays[plays["yards_gained"].notna()]
    explosive = ((known["play_type"] == "run") & (known["yards_gained"] >= EXPLOSIVE_RUN_YARDS)) | (
        (known["play_type"] == "pass") & (known["yards_gained"] >= EXPLOSIVE_PASS_YARDS)
    )
    return {"explosive_play_rate": ratio(float(explosive.sum()), len(known))}


def turnover_metrics(plays: pd.DataFrame, games: int) -> dict[str, MetricValue]:
    turnovers = _true(plays["interception"]).sum() + _true(plays["fumble_lost"]).sum()
    return {"turnovers_per_game": ratio(float(turnovers), games)}


def compute_team_metrics(df: pd.DataFrame, *, min_sample: int = 30) -> TeamMetrics:
    """All M1 metrics for an already filtered set of one team's plays."""
    plays = scrimmage_plays(df)
    games = int(plays["game_id"].nunique())
    metrics = {
        **efficiency_metrics(plays),
        **third_down_metrics(plays),
        **explosive_metrics(plays),
        **turnover_metrics(plays, games),
    }
    warnings: list[str] = []
    if len(plays) == 0:
        warnings.append("No plays match these filters")
    elif len(plays) < min_sample:
        warnings.append(f"Sample under {min_sample} plays")
    warnings += [
        f"{name} unavailable: no qualifying plays"
        for name, metric in metrics.items()
        if metric.value is None and len(plays) > 0
    ]
    return TeamMetrics(plays=len(plays), games=games, metrics=metrics, warnings=warnings)
