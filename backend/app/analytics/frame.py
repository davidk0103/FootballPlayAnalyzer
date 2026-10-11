"""The standard play frame every analytics function works on.

Public nflverse plays and user-uploaded plays are both converted to this shape, so
the same pure-pandas code computes metrics for either. Indicator columns use pandas'
nullable ``boolean`` dtype: <NA> means "unknown", which is never treated as False
when it matters (metrics drop unknowns from their denominators).
"""

from enum import StrEnum

import pandas as pd

INT_COLUMNS = (
    "season",
    "week",
    "qtr",
    "down",
    "yards_to_go",
    "yard_line_100",
    "score_differential",
    "game_seconds_remaining",
    "yards_gained",
    "passing_yards",
    "rushing_yards",
    "receiving_yards",
)
FLOAT_COLUMNS = ("epa",)
BOOL_COLUMNS = (
    "success",
    "complete_pass",
    "incomplete_pass",
    "pass_attempt",
    "rush_attempt",
    "sack",
    "qb_scramble",
    "touchdown",
    "interception",
    "fumble_lost",
    "first_down",
    "first_down_penalty",
    "penalty",
    "third_down_converted",
    "third_down_failed",
    "fourth_down_converted",
    "two_point_attempt",
    "play_deleted",
)
STRING_COLUMNS = (
    "game_key",
    "season_type",
    "offense",
    "defense",
    "play_type",
    "passer_id",
    "rusher_id",
    "receiver_id",
)
FRAME_COLUMNS = STRING_COLUMNS + INT_COLUMNS + FLOAT_COLUMNS + BOOL_COLUMNS


class Side(StrEnum):
    OFFENSE = "offense"
    DEFENSE = "defense"


def coerce_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a frame with every standard column present and typed (missing -> <NA>)."""
    out = pd.DataFrame(index=df.index)
    for col in STRING_COLUMNS:
        out[col] = (
            df[col].astype("string")
            if col in df
            else pd.Series(pd.NA, index=df.index, dtype="string")
        )
    for col in INT_COLUMNS:
        out[col] = (
            pd.to_numeric(df[col], errors="coerce").round().astype("Int64")
            if col in df
            else pd.Series(pd.NA, index=df.index, dtype="Int64")
        )
    for col in FLOAT_COLUMNS:
        out[col] = (
            pd.to_numeric(df[col], errors="coerce").astype("Float64")
            if col in df
            else pd.Series(pd.NA, index=df.index, dtype="Float64")
        )
    for col in BOOL_COLUMNS:
        out[col] = (
            df[col].astype("boolean")
            if col in df
            else pd.Series(pd.NA, index=df.index, dtype="boolean")
        )
    return out


def flag(series: "pd.Series[bool]") -> "pd.Series[bool]":
    """Nullable indicator as plain bool, unknown -> False (for counting numerators)."""
    return series.astype("boolean").fillna(False).astype(bool)


def team_view(df: pd.DataFrame, team: str | None, side: Side) -> pd.DataFrame:
    """Plays from one side's perspective, adding ``team``, ``opponent``, ``team_score_diff``.

    With ``team=None`` the whole league is returned from that side's perspective (every
    play once), which is what league averages and rankings are computed from.
    ``score_differential`` in nflverse is the offense's margin, so it is negated when
    looking at a defense.
    """
    if side == Side.OFFENSE:
        out = (df if team is None else df[(df["offense"] == team).fillna(False)]).copy()
        out["team"] = out["offense"]
        out["opponent"] = out["defense"]
        out["team_score_diff"] = out["score_differential"]
    else:
        out = (df if team is None else df[(df["defense"] == team).fillna(False)]).copy()
        out["team"] = out["defense"]
        out["opponent"] = out["offense"]
        out["team_score_diff"] = -out["score_differential"]
    return out
