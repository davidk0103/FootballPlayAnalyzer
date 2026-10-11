import pandas as pd
import pytest

from app.analytics.frame import Side, coerce_frame, team_view
from app.analytics.report import Inputs, build_report, red_zone
from app.reports.export import safe_cell


def plays(team_epa: dict[str, float], n: int = 40) -> pd.DataFrame:
    """``n`` passes per team against a dummy opponent, each worth the given EPA."""
    rows = []
    for team, epa in team_epa.items():
        for i in range(n):
            rows.append(
                {
                    "game_key": f"{team}-{i % 4}",
                    "offense": team,
                    "defense": "OPP" if team != "OPP" else "AAA",
                    "play_type": "pass",
                    "down": 1 + i % 4 if i % 4 != 3 else 3,
                    "yards_to_go": 5,
                    "yard_line_100": 10 if i % 5 == 0 else 50,
                    "yards_gained": 6,
                    "epa": epa,
                    "success": epa > 0,
                    "touchdown": i % 10 == 0,
                    "interception": False,
                    "fumble_lost": False,
                    "third_down_converted": i % 2 == 0,
                }
            )
    return coerce_frame(pd.DataFrame(rows))


def inputs(df: pd.DataFrame, team: str) -> Inputs:
    return Inputs(
        team=team,
        offense=team_view(df, team, Side.OFFENSE),
        league_offense=team_view(df, None, Side.OFFENSE),
        defense=team_view(df, team, Side.DEFENSE),
        league_defense=team_view(df, None, Side.DEFENSE),
    )


def test_findings_flag_top_and_bottom_thirds() -> None:
    df = plays({"AAA": 0.5, "BBB": 0.1, "CCC": 0.0, "DDD": -0.1, "EEE": -0.4, "FFF": 0.05})
    best = build_report(inputs(df, "AAA"), min_sample=30)
    epa = next(m for m in best.offense.metrics if m.name == "epa_per_play")
    assert (epa.rank, epa.of, epa.better) == (1, 6, "higher")
    kinds = {(f.side, f.metric): f.kind for f in best.findings}
    assert kinds[("offense", "epa_per_play")] == "strength"
    worst = build_report(inputs(df, "EEE"), min_sample=30)
    assert {(f.metric, f.kind) for f in worst.findings} >= {("epa_per_play", "weakness")}
    middle = build_report(inputs(df, "CCC"), min_sample=30)
    assert ("offense", "epa_per_play") not in {(f.side, f.metric) for f in middle.findings}


def test_small_samples_and_few_teams_produce_no_rank_findings() -> None:
    df = plays({"AAA": 0.5, "BBB": -0.5}, n=10)
    report = build_report(inputs(df, "AAA"), min_sample=30)
    assert report.findings == []
    assert all(m.rank is None for m in report.offense.metrics)
    assert any("Only 10 offense plays" in w for w in report.warnings)
    assert any("ranks and strength/weakness findings need" in x for x in report.limitations)


def test_report_is_deterministic() -> None:
    df = plays({"AAA": 0.2, "BBB": 0.1, "CCC": 0.0, "DDD": -0.1})
    assert build_report(inputs(df, "BBB")) == build_report(inputs(df, "BBB"))


def test_red_zone_counts_only_inside_the_20() -> None:
    df = team_view(plays({"AAA": 0.1}, n=20), "AAA", Side.OFFENSE)
    rz = red_zone(df)
    assert rz.plays == 4  # every 5th play is at the 10
    assert rz.touchdown_rate.denominator == 4


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+SUM(A1)", "'+SUM(A1)"),
        ("-2+3", "'-2+3"),
        ("@cmd", "'@cmd"),
        ("\tx", "'\tx"),
        ("DET", "DET"),
        (-0.25, -0.25),
        (3, 3),
        (None, ""),
        (True, "true"),
    ],
)
def test_safe_cell(value: object, expected: object) -> None:
    assert safe_cell(value) == expected
