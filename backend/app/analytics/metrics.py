"""Team metrics computed from play frames. Pure pandas, no database or HTTP.

Input frames follow ``frame.FRAME_COLUMNS``. Every rate is returned with its numerator
and denominator, and is ``None`` (never 0) when nothing qualifies.
"""

from dataclasses import dataclass, field

import pandas as pd

from app.analytics.frame import flag

SCRIMMAGE_PLAY_TYPES = ("pass", "run")
EXPLOSIVE_RUN_YARDS = 10
EXPLOSIVE_PASS_YARDS = 20


@dataclass(frozen=True)
class Thresholds:
    """Explosive-play cutoffs. Configurable per request; defaults follow common usage."""

    run_yards: int = EXPLOSIVE_RUN_YARDS
    pass_yards: int = EXPLOSIVE_PASS_YARDS

    @property
    def is_default(self) -> bool:
        return (self.run_yards, self.pass_yards) == (EXPLOSIVE_RUN_YARDS, EXPLOSIVE_PASS_YARDS)


DEFAULT_THRESHOLDS = Thresholds()

THIRD_DOWN_DEFINITION = (
    "Third-down scrimmage plays where the offense earned a first down or touchdown on "
    "the play (nflverse third_down_converted), plus plays that stood with an accepted "
    "defensive penalty awarding a first down / all third-down scrimmage plays. Defensive "
    "return touchdowns are failures. Plays wiped out by penalty (no_play) are excluded "
    "from both sides."
)


def definitions(thresholds: Thresholds = DEFAULT_THRESHOLDS) -> dict[str, str]:
    return {
        "epa_per_play": (
            "Sum of expected points added / scrimmage plays with EPA. Scrimmage plays are "
            "passes (incl. sacks) and runs (incl. scrambles), excluding penalties that "
            "nullified the play, kneels, spikes, and two-point tries."
        ),
        "success_rate": (
            "Share of scrimmage plays with positive EPA (the nflverse definition of "
            "success, not the 40/60/100% down-based rule)."
        ),
        "yards_per_play": "Total yards gained / scrimmage plays.",
        "pass_rate": "Pass plays (including sacks) / scrimmage plays.",
        "first_down_rate": "Scrimmage plays that gained a first down (incl. by penalty) / plays.",
        "third_down_conversion_rate": THIRD_DOWN_DEFINITION,
        "explosive_play_rate": (
            f"Runs of {thresholds.run_yards}+ yards or passes of {thresholds.pass_yards}+ "
            "yards / scrimmage plays with known yardage. Thresholds are configurable"
            + (" (defaults shown)." if thresholds.is_default else " (custom values shown).")
        ),
        "turnovers_per_game": "(Interceptions + fumbles lost) / games in the sample.",
    }


DEFINITIONS = definitions()


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
        value=value, numerator=round(float(numerator), digits), denominator=int(denominator)
    )


def scrimmage_plays(df: pd.DataFrame) -> pd.DataFrame:
    mask = (
        df["play_type"].isin(SCRIMMAGE_PLAY_TYPES).fillna(False)
        & ~flag(df["two_point_attempt"])
        & ~flag(df["play_deleted"])
    )
    return df[mask.astype(bool)]


def efficiency_metrics(plays: pd.DataFrame) -> dict[str, MetricValue]:
    with_epa = plays["epa"].dropna()
    with_success = plays["success"].dropna()
    with_yards = plays["yards_gained"].dropna()
    return {
        "epa_per_play": ratio(float(with_epa.sum()), len(with_epa)),
        "success_rate": ratio(float(flag(with_success).sum()), len(with_success)),
        "yards_per_play": ratio(float(with_yards.sum()), len(with_yards)),
        "pass_rate": ratio(float((plays["play_type"] == "pass").sum()), len(plays)),
    }


def first_down_metrics(plays: pd.DataFrame) -> dict[str, MetricValue]:
    known = plays["first_down"].dropna()
    return {"first_down_rate": ratio(float(flag(known).sum()), len(known))}


def third_down_converted(plays: pd.DataFrame) -> "pd.Series[bool]":
    return flag(plays["third_down_converted"]) | flag(plays["first_down_penalty"])


def third_down_metrics(plays: pd.DataFrame) -> dict[str, MetricValue]:
    third = plays[(plays["down"] == 3).fillna(False).astype(bool)]
    known = third[third["third_down_converted"].notna()]
    return {
        "third_down_conversion_rate": ratio(float(third_down_converted(known).sum()), len(known))
    }


def explosive_mask(plays: pd.DataFrame, thresholds: Thresholds) -> "pd.Series[bool]":
    yards = plays["yards_gained"]
    is_run = (plays["play_type"] == "run").fillna(False)
    is_pass = (plays["play_type"] == "pass").fillna(False)
    out = (is_run & (yards >= thresholds.run_yards)) | (is_pass & (yards >= thresholds.pass_yards))
    return out.fillna(False).astype(bool)


def explosive_metrics(
    plays: pd.DataFrame, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> dict[str, MetricValue]:
    known = plays[plays["yards_gained"].notna()]
    return {
        "explosive_play_rate": ratio(float(explosive_mask(known, thresholds).sum()), len(known))
    }


def turnover_metrics(plays: pd.DataFrame, games: int) -> dict[str, MetricValue]:
    turnovers = flag(plays["interception"]).sum() + flag(plays["fumble_lost"]).sum()
    return {"turnovers_per_game": ratio(float(turnovers), games)}


def sample_warnings(plays: int, min_sample: int) -> list[str]:
    if plays == 0:
        return ["No plays match these filters"]
    if plays < min_sample:
        return [f"Sample under {min_sample} plays"]
    return []


def compute_team_metrics(
    df: pd.DataFrame, *, min_sample: int = 30, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> TeamMetrics:
    """The headline metrics for an already filtered set of one team's plays."""
    plays = scrimmage_plays(df)
    games = int(plays["game_key"].nunique())
    metrics = {
        **efficiency_metrics(plays),
        **third_down_metrics(plays),
        **explosive_metrics(plays, thresholds),
        **turnover_metrics(plays, games),
    }
    warnings = sample_warnings(len(plays), min_sample)
    warnings += [
        f"{name} unavailable: no qualifying plays"
        for name, metric in metrics.items()
        if metric.value is None and len(plays) > 0
    ]
    return TeamMetrics(plays=len(plays), games=games, metrics=metrics, warnings=warnings)


def situation_metrics(
    plays: pd.DataFrame, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> dict[str, MetricValue]:
    """Per-situation metrics (no per-game rates: a situation is not a whole game)."""
    return {
        **efficiency_metrics(plays),
        **first_down_metrics(plays),
        **explosive_metrics(plays, thresholds),
    }
