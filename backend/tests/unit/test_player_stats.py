from typing import Any

import pandas as pd

from app.analytics.frame import coerce_frame
from app.analytics.players import player_stats, top_players

QB, RB, WR = "qb", "rb", "wr"


def play(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "game_key": "g1",
        "offense": "DET",
        "defense": "KC",
        "play_type": "pass",
        "pass_attempt": False,
        "rush_attempt": False,
        "sack": False,
        "complete_pass": False,
        "touchdown": False,
        "fumble_lost": False,
        "interception": False,
        "two_point_attempt": False,
        "play_deleted": False,
        "epa": 0.0,
    }
    base.update(overrides)
    return base


def frame(*rows: dict[str, Any]) -> pd.DataFrame:
    return coerce_frame(pd.DataFrame(list(rows)))


def test_passing_counting_rules() -> None:
    df = frame(
        play(
            passer_id=QB,
            receiver_id=WR,
            pass_attempt=True,
            complete_pass=True,
            passing_yards=30,
            receiving_yards=30,
            touchdown=True,
        ),
        play(passer_id=QB, receiver_id=WR, pass_attempt=True),
        # Spike: an official pass attempt.
        play(play_type="qb_spike", passer_id=QB, pass_attempt=True),
        # Sack: not an attempt, sack yards not deducted.
        play(passer_id=QB, pass_attempt=True, sack=True, yards_gained=-8),
        # Two-point try: never counted.
        play(
            passer_id=QB,
            receiver_id=WR,
            pass_attempt=True,
            complete_pass=True,
            passing_yards=2,
            two_point_attempt=True,
        ),
        play(passer_id=QB, receiver_id=WR, pass_attempt=True, interception=True),
    )
    stats = player_stats(df, QB)
    p = stats.passing
    assert p["pass_attempts"] == 4
    assert p["completions"] == 1
    assert p["passing_yards"] == 30
    assert p["passing_touchdowns"] == 1
    assert p["interceptions"] == 1
    assert p["sacks"] == 1
    receiving = player_stats(df, WR).receiving
    assert receiving["targets"] == 3
    assert receiving["receptions"] == 1
    assert receiving["receiving_yards"] == 30


def test_rushing_counts_kneels_and_scrambles() -> None:
    df = frame(
        play(play_type="run", rusher_id=RB, rush_attempt=True, rushing_yards=12),
        play(play_type="qb_kneel", rusher_id=QB, rush_attempt=True, rushing_yards=-1),
        play(play_type="run", rusher_id=QB, rush_attempt=True, rushing_yards=9),
        play(
            play_type="run",
            rusher_id=RB,
            rush_attempt=True,
            rushing_yards=3,
            touchdown=True,
            fumble_lost=True,
        ),
    )
    qb = player_stats(df, QB).rushing
    assert (qb["rush_attempts"], qb["rushing_yards"]) == (2, 8)
    rb = player_stats(df, RB).rushing
    assert rb["rushing_touchdowns"] == 0
    assert rb["yards_per_carry"].value == 7.5  # type: ignore[union-attr]


def test_no_plays_gives_null_rates() -> None:
    stats = player_stats(frame(play(passer_id="other", pass_attempt=True)), QB)
    assert stats.plays == 0
    assert stats.passing["completion_rate"].value is None  # type: ignore[union-attr]


def test_top_players_orders_by_yards() -> None:
    df = frame(
        play(play_type="run", rusher_id="a", rush_attempt=True, rushing_yards=10),
        play(play_type="run", rusher_id="b", rush_attempt=True, rushing_yards=50),
        play(play_type="run", rusher_id="b", rush_attempt=True, rushing_yards=5),
        play(play_type="run", rusher_id="c", rush_attempt=True, rushing_yards=99, offense="KC"),
    )
    leaders = top_players(df, "DET")["rushing"]
    assert leaders == [("b", 2, 55), ("a", 1, 10)]
