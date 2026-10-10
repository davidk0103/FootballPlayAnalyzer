from typing import Any

import pandas as pd
import pytest

from app.analytics.filters import (
    Distance,
    FieldZone,
    PlayFilters,
    PlayType,
    SeasonType,
    apply_filters,
)
from app.analytics.metrics import (
    compute_team_metrics,
    explosive_metrics,
    ratio,
    scrimmage_plays,
    third_down_metrics,
)


def play(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "game_id": 1,
        "season_type": "REG",
        "play_type": "pass",
        "down": 1,
        "yards_to_go": 10,
        "yard_line_100": 75,
        "qtr": 1,
        "yards_gained": 5,
        "epa": 0.5,
        "success": True,
        "interception": False,
        "fumble_lost": False,
        "third_down_converted": False,
        "two_point_attempt": False,
        "play_deleted": False,
    }
    base.update(overrides)
    return base


def frame(*rows: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_ratio_zero_denominator_is_null_not_zero() -> None:
    result = ratio(0.0, 0)
    assert result.value is None
    assert result.denominator == 0


def test_scrimmage_excludes_special_teams_two_point_and_deleted() -> None:
    df = frame(
        play(),
        play(play_type="run"),
        play(play_type="punt"),
        play(play_type="qb_kneel"),
        play(play_type="pass", two_point_attempt=True, down=None),
        play(play_type="run", play_deleted=True),
    )
    assert len(scrimmage_plays(df)) == 2


def test_efficiency_metrics_known_answers() -> None:
    df = frame(
        play(epa=1.0, success=True, yards_gained=12),
        play(epa=-0.5, success=False, yards_gained=0, play_type="run"),
        play(epa=0.25, success=True, yards_gained=3),
        play(epa=-0.75, success=False, yards_gained=-7),
    )
    m = compute_team_metrics(df, min_sample=1).metrics
    assert m["epa_per_play"].value == 0.0
    assert m["epa_per_play"].numerator == 0.0
    assert m["epa_per_play"].denominator == 4
    assert m["success_rate"].value == 0.5
    assert m["yards_per_play"].value == 2.0
    assert m["pass_rate"].value == 0.75


def test_null_epa_is_excluded_from_denominator() -> None:
    df = frame(play(epa=1.0), play(epa=None, success=None), play(epa=-0.4, success=False))
    m = compute_team_metrics(df, min_sample=1).metrics
    assert m["epa_per_play"].denominator == 2
    assert m["epa_per_play"].value == 0.3
    assert m["success_rate"].denominator == 2
    assert m["success_rate"].value == 0.5


def test_all_null_epa_gives_null_metric_and_warning() -> None:
    df = frame(play(epa=None, success=None), play(epa=None, success=None))
    result = compute_team_metrics(df, min_sample=1)
    assert result.metrics["epa_per_play"].value is None
    assert "epa_per_play unavailable: no qualifying plays" in result.warnings


def test_third_down_conversion() -> None:
    df = frame(
        play(down=3, third_down_converted=True),
        play(down=3, third_down_converted=False),
        play(down=3, third_down_converted=False),
        play(down=3, third_down_converted=None),
        play(down=2, third_down_converted=False),
    )
    m = third_down_metrics(scrimmage_plays(df))["third_down_conversion_rate"]
    assert (m.numerator, m.denominator) == (1.0, 3)
    assert m.value == pytest.approx(0.3333)


def test_third_down_without_third_downs_is_null() -> None:
    m = third_down_metrics(frame(play(down=1)))["third_down_conversion_rate"]
    assert m.value is None


@pytest.mark.parametrize(
    ("play_type", "yards", "explosive"),
    [("run", 9, False), ("run", 10, True), ("pass", 19, False), ("pass", 20, True)],
)
def test_explosive_thresholds(play_type: str, yards: int, explosive: bool) -> None:
    m = explosive_metrics(frame(play(play_type=play_type, yards_gained=yards)))
    assert m["explosive_play_rate"].value == (1.0 if explosive else 0.0)


def test_turnovers_per_game() -> None:
    df = frame(
        play(game_id=1, interception=True),
        play(game_id=1, fumble_lost=True),
        play(game_id=2),
    )
    result = compute_team_metrics(df, min_sample=1)
    assert result.games == 2
    assert result.metrics["turnovers_per_game"].value == 1.0


def test_empty_sample_returns_nulls_and_single_warning() -> None:
    result = compute_team_metrics(frame(play(play_type="punt")))
    assert result.plays == 0
    assert all(m.value is None for m in result.metrics.values())
    assert result.warnings == ["No plays match these filters"]


def test_small_sample_warning() -> None:
    result = compute_team_metrics(frame(play(), play()), min_sample=30)
    assert "Sample under 30 plays" in result.warnings


@pytest.mark.parametrize(
    ("distance", "ytg", "kept"),
    [
        (Distance.SHORT, 1, True),
        (Distance.SHORT, 3, True),
        (Distance.SHORT, 4, False),
        (Distance.MEDIUM, 4, True),
        (Distance.MEDIUM, 7, True),
        (Distance.LONG, 8, True),
        (Distance.LONG, 7, False),
    ],
)
def test_distance_buckets(distance: Distance, ytg: int, kept: bool) -> None:
    df = frame(play(yards_to_go=ytg))
    assert len(apply_filters(df, PlayFilters(season=2023, distance=distance))) == int(kept)


@pytest.mark.parametrize(
    ("zone", "yardline", "kept"),
    [
        (FieldZone.RED_ZONE, 20, True),
        (FieldZone.RED_ZONE, 21, False),
        (FieldZone.OPP, 21, True),
        (FieldZone.OPP, 49, True),
        (FieldZone.OWN, 50, True),
        (FieldZone.OWN, 79, True),
        (FieldZone.OWN_DEEP, 80, True),
        (FieldZone.OWN_DEEP, None, False),
    ],
)
def test_field_zones(zone: FieldZone, yardline: int | None, kept: bool) -> None:
    df = frame(play(yard_line_100=yardline))
    assert len(apply_filters(df, PlayFilters(season=2023, field_zone=zone))) == int(kept)


def test_combined_filters() -> None:
    df = frame(
        play(down=3, qtr=4, play_type="pass", season_type="REG"),
        play(down=3, qtr=4, play_type="run", season_type="REG"),
        play(down=3, qtr=1, play_type="pass", season_type="REG"),
        play(down=2, qtr=4, play_type="pass", season_type="REG"),
        play(down=3, qtr=4, play_type="pass", season_type="POST"),
    )
    filters = PlayFilters(
        season=2023,
        down=(3,),
        qtr=(4, 5),
        play_type=PlayType.PASS,
        season_type=SeasonType.REG,
    )
    assert len(apply_filters(df, filters)) == 1
    assert filters.as_dict() == {
        "season": 2023,
        "side": "offense",
        "season_type": "REG",
        "down": [3],
        "qtr": [4, 5],
        "play_type": "pass",
    }
