"""Validate and reshape raw nflverse rows. Pure pandas, no database access."""

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.ingest.teams import FRANCHISE_ALIASES, TEAM_ABBREVIATIONS

BOOL_COLUMNS: dict[str, str] = {
    "success": "success",
    "pass": "is_pass",
    "rush": "is_rush",
    "complete_pass": "complete_pass",
    "incomplete_pass": "incomplete_pass",
    "pass_attempt": "pass_attempt",
    "rush_attempt": "rush_attempt",
    "sack": "sack",
    "qb_scramble": "qb_scramble",
    "touchdown": "touchdown",
    "interception": "interception",
    "fumble_lost": "fumble_lost",
    "first_down": "first_down",
    "first_down_penalty": "first_down_penalty",
    "penalty": "penalty",
    "third_down_converted": "third_down_converted",
    "third_down_failed": "third_down_failed",
    "fourth_down_converted": "fourth_down_converted",
    "two_point_attempt": "two_point_attempt",
    "aborted_play": "aborted_play",
    "play_deleted": "play_deleted",
}
INT_COLUMNS: dict[str, str] = {
    "play_id": "external_play_id",
    "season": "season",
    "week": "week",
    "qtr": "qtr",
    "game_seconds_remaining": "game_seconds_remaining",
    "down": "down",
    "ydstogo": "yards_to_go",
    "yardline_100": "yard_line_100",
    "score_differential": "score_differential",
    "yards_gained": "yards_gained",
    "passing_yards": "passing_yards",
    "rushing_yards": "rushing_yards",
    "receiving_yards": "receiving_yards",
}
PASSTHROUGH_COLUMNS: dict[str, str] = {
    "game_id": "external_game_id",
    "season_type": "season_type",
    "play_type": "play_type",
    "epa": "epa",
    "posteam": "offense_team",
    "defteam": "defense_team",
    "passer_player_id": "passer_external_id",
    "rusher_player_id": "rusher_external_id",
    "receiver_player_id": "receiver_external_id",
}
NOT_STORED_PLAY_TYPES = frozenset({"no_play"})
VALID_SEASON_TYPES = frozenset({"REG", "POST"})


@dataclass
class Rejection:
    source_row_ref: str
    reason: str
    raw: dict[str, Any]


@dataclass
class TransformResult:
    plays: pd.DataFrame
    games: pd.DataFrame
    rejected: list[Rejection] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy scalars to JSON-serialisable Python values; missing -> None."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(k): json_safe(v) for k, v in row.items()} for row in df.to_dict("records")]


def _row_ref(row: pd.Series) -> str:
    return f"{json_safe(row.get('game_id'))}:{json_safe(row.get('play_id'))}"


def _is_whole(series: pd.Series) -> pd.Series:
    return series.isna() | (series == series.round())


TEAM_COLUMNS = ("home_team", "away_team", "posteam", "defteam")


def rejection_reasons(df: pd.DataFrame, season: int) -> pd.Series:
    """Return the first failing validation reason per row (empty string when valid)."""
    reasons = pd.Series("", index=df.index, dtype=object)

    def mark(mask: pd.Series, reason: str) -> None:
        reasons.loc[mask & (reasons == "")] = reason

    for col in ("game_id", "play_id", "season", "week", "season_type", "home_team", "away_team"):
        mark(df[col].isna(), f"missing {col}")
    mark(df["season"].notna() & (df["season"] != season), f"season does not match {season}")
    mark(~df["season_type"].isin(VALID_SEASON_TYPES), "unknown season_type")
    for col in TEAM_COLUMNS:
        mark(df[col].notna() & ~df[col].isin(TEAM_ABBREVIATIONS), f"unknown team in {col}")
    mark(df["down"].notna() & ~df["down"].isin([1, 2, 3, 4]), "down out of range")
    mark(df["qtr"].notna() & ~df["qtr"].isin([1, 2, 3, 4, 5]), "qtr out of range")
    mark(
        df["yardline_100"].notna() & ~df["yardline_100"].between(0, 100),
        "yardline_100 out of range",
    )
    for col in INT_COLUMNS:
        mark(~_is_whole(df[col]), f"non-integer {col}")
    mark(df.duplicated(["game_id", "play_id"], keep="first"), "duplicate (game_id, play_id)")
    return reasons


def transform(raw: pd.DataFrame, season: int) -> TransformResult:
    """Split raw nflverse rows into storable plays, game rows, rejections, and skip counts."""
    skipped = {
        "null_play_type": int(raw["play_type"].isna().sum()),
        "no_play": int(raw["play_type"].isin(NOT_STORED_PLAY_TYPES).sum()),
    }
    candidates = raw[
        raw["play_type"].notna() & ~raw["play_type"].isin(NOT_STORED_PLAY_TYPES)
    ].copy()
    for col in TEAM_COLUMNS:
        candidates[col] = candidates[col].replace(FRANCHISE_ALIASES)

    reasons = rejection_reasons(candidates, season)
    bad = candidates[reasons != ""]
    rejected = [
        Rejection(
            source_row_ref=_row_ref(row),
            reason=str(reason),
            raw={str(k): json_safe(v) for k, v in row.items()},
        )
        for (_, row), reason in zip(bad.iterrows(), reasons[reasons != ""], strict=True)
    ]
    good = candidates[reasons == ""]

    out = pd.DataFrame(index=good.index)
    for src, dst in PASSTHROUGH_COLUMNS.items():
        out[dst] = good[src].astype(object).where(good[src].notna(), None)
    for src, dst in INT_COLUMNS.items():
        out[dst] = good[src].astype("Int64")
    for src, dst in BOOL_COLUMNS.items():
        out[dst] = good[src].astype("Float64").astype("boolean")

    games = (
        good[["game_id", "season", "season_type", "week", "game_date", "home_team", "away_team"]]
        .drop_duplicates("game_id")
        .rename(columns={"game_id": "external_game_id"})
        .reset_index(drop=True)
    )
    games["season"] = games["season"].astype("Int64")
    games["week"] = games["week"].astype("Int64")
    games["game_date"] = pd.to_datetime(games["game_date"], errors="coerce").dt.date

    return TransformResult(
        plays=out.reset_index(drop=True), games=games, rejected=rejected, skipped=skipped
    )
