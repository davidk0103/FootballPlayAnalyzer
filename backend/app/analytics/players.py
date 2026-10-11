"""Player passing, rushing, and receiving stats from the official-stat yardage columns.

Counting rules (checked against official 2024 box-score totals, see docs/data.md):
- every stored play counts except two-point tries and deleted plays, so kneels count as
  rushes and spikes as pass attempts, as in official statistics;
- pass attempts exclude sacks; passing yards are not reduced by sack yardage;
- plays wiped out by penalty are not stored, so they never count.
"""

from dataclasses import dataclass

import pandas as pd

from app.analytics.frame import flag
from app.analytics.metrics import MetricValue, ratio

DEFINITIONS: dict[str, str] = {
    "pass_attempts": "Passes thrown, including spikes, excluding sacks and two-point tries.",
    "completion_rate": "Completions / pass attempts.",
    "passing_yards": "Official passing yards (nflverse passing_yards; sack yardage not deducted).",
    "yards_per_attempt": "Passing yards / pass attempts.",
    "passing_touchdowns": "Completed passes that ended in a touchdown with no lost fumble.",
    "sacks": "Times sacked as the passer.",
    "epa_per_dropback": "EPA / dropbacks (pass attempts plus sacks) with EPA.",
    "rush_attempts": "Official rushing attempts, including kneels and scrambles.",
    "rushing_yards": "Official rushing yards (nflverse rushing_yards).",
    "yards_per_carry": "Rushing yards / rush attempts.",
    "rushing_touchdowns": "Rushes that ended in a touchdown with no lost fumble.",
    "epa_per_rush": "EPA / rush attempts with EPA.",
    "targets": "Pass attempts (not sacks) with this player as the intended receiver.",
    "receptions": "Completed passes to this player.",
    "catch_rate": "Receptions / targets.",
    "receiving_yards": "Official receiving yards (nflverse receiving_yards).",
    "yards_per_target": "Receiving yards / targets.",
    "receiving_touchdowns": "Receptions that ended in a touchdown with no lost fumble.",
    "epa_per_target": "EPA / targets with EPA.",
}

LIMITATIONS = [
    "Totals come from nflverse play-by-play and can differ from official records by a "
    "few yards when the league later corrects a play.",
    "Touchdowns are attributed to the passer/rusher/receiver of a scoring play without a "
    "lost fumble; a touchdown after a lateral is credited to the original ball carrier.",
    "Throwaways without an intended receiver count as pass attempts but not as targets.",
    "Fumbles are not attributed to individual players in the stored data.",
    "Only seasons that have been imported are available.",
]


def _sum(series: "pd.Series[int]") -> int:
    return int(series.fillna(0).sum())


def _epa(df: pd.DataFrame) -> MetricValue:
    known = df["epa"].dropna()
    return ratio(float(known.sum()), len(known))


@dataclass
class PlayerStats:
    plays: int
    games: int
    teams: list[str]
    passing: dict[str, int | MetricValue]
    rushing: dict[str, int | MetricValue]
    receiving: dict[str, int | MetricValue]


def counted_plays(df: pd.DataFrame) -> pd.DataFrame:
    return df[~flag(df["two_point_attempt"]) & ~flag(df["play_deleted"])]


def player_stats(frame: pd.DataFrame, player_id: str) -> PlayerStats:
    """Stats for one player (gsis id) over an already filtered standard frame."""
    df = counted_plays(frame)
    as_passer = df[(df["passer_id"] == player_id).fillna(False).astype(bool)]
    as_rusher = df[(df["rusher_id"] == player_id).fillna(False).astype(bool)]
    as_receiver = df[(df["receiver_id"] == player_id).fillna(False).astype(bool)]

    sacked = flag(as_passer["sack"])
    attempts = as_passer[flag(as_passer["pass_attempt"]) & ~sacked]
    completions = attempts[flag(attempts["complete_pass"])]
    pass_yards = _sum(as_passer["passing_yards"])
    dropbacks = as_passer[(flag(as_passer["pass_attempt"]) | sacked)]
    passing: dict[str, int | MetricValue] = {
        "pass_attempts": len(attempts),
        "completions": len(completions),
        "completion_rate": ratio(len(completions), len(attempts)),
        "passing_yards": pass_yards,
        "yards_per_attempt": ratio(pass_yards, len(attempts), digits=2),
        "passing_touchdowns": int(
            (flag(completions["touchdown"]) & ~flag(completions["fumble_lost"])).sum()
        ),
        "interceptions": int(flag(attempts["interception"]).sum()),
        "sacks": int(sacked.sum()),
        "epa_per_dropback": _epa(dropbacks),
    }

    rushes = as_rusher[flag(as_rusher["rush_attempt"])]
    rush_yards = _sum(rushes["rushing_yards"])
    rushing: dict[str, int | MetricValue] = {
        "rush_attempts": len(rushes),
        "rushing_yards": rush_yards,
        "yards_per_carry": ratio(rush_yards, len(rushes), digits=2),
        "rushing_touchdowns": int((flag(rushes["touchdown"]) & ~flag(rushes["fumble_lost"])).sum()),
        "epa_per_rush": _epa(rushes),
    }

    targets = as_receiver[flag(as_receiver["pass_attempt"]) & ~flag(as_receiver["sack"])]
    receptions = targets[flag(targets["complete_pass"])]
    rec_yards = _sum(as_receiver["receiving_yards"])
    receiving: dict[str, int | MetricValue] = {
        "targets": len(targets),
        "receptions": len(receptions),
        "catch_rate": ratio(len(receptions), len(targets)),
        "receiving_yards": rec_yards,
        "yards_per_target": ratio(rec_yards, len(targets), digits=2),
        "yards_per_reception": ratio(rec_yards, len(receptions), digits=2),
        "receiving_touchdowns": int(
            (flag(receptions["touchdown"]) & ~flag(receptions["fumble_lost"])).sum()
        ),
        "epa_per_target": _epa(targets),
    }

    involved = pd.concat([as_passer, as_rusher, as_receiver])
    involved = involved[~involved.index.duplicated()]
    teams = involved["offense"].dropna().value_counts()
    return PlayerStats(
        plays=len(involved),
        games=int(involved["game_key"].nunique()),
        teams=[str(t) for t in teams.index],
        passing=passing,
        rushing=rushing,
        receiving=receiving,
    )


def top_players(
    frame: pd.DataFrame, team: str, *, limit: int = 3
) -> dict[str, list[tuple[str, int, int]]]:
    """Leaders for a team's offense: (player_id, volume, yards) by passing/rushing/receiving."""
    df = counted_plays(frame)
    df = df[(df["offense"] == team).fillna(False).astype(bool)]
    out: dict[str, list[tuple[str, int, int]]] = {}
    specs = (
        ("passing", "passer_id", "passing_yards", flag(df["pass_attempt"]) & ~flag(df["sack"])),
        ("rushing", "rusher_id", "rushing_yards", flag(df["rush_attempt"])),
        (
            "receiving",
            "receiver_id",
            "receiving_yards",
            flag(df["pass_attempt"]) & ~flag(df["sack"]),
        ),
    )
    for name, id_col, yards_col, volume_mask in specs:
        rows = df[df[id_col].notna()]
        grouped = (
            pd.DataFrame(
                {
                    "volume": volume_mask[rows.index].astype(int),
                    "yards": rows[yards_col].fillna(0).astype(int),
                    "player": rows[id_col],
                }
            )
            .groupby("player", observed=True)[["volume", "yards"]]
            .sum()
        )
        grouped = grouped.sort_values(["yards", "volume"], ascending=False).head(limit)
        out[name] = [(str(pid), int(r.volume), int(r.yards)) for pid, r in grouped.iterrows()]
    return out
