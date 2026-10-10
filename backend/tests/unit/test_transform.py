import numpy as np
import pandas as pd

from app.ingest.columns import REQUIRED_COLUMNS
from app.ingest.transform import json_safe, rejection_reasons, transform
from tests.conftest import PBP_SAMPLE


def sample() -> pd.DataFrame:
    return pd.read_parquet(PBP_SAMPLE, columns=REQUIRED_COLUMNS)


def test_transform_skips_no_play_and_null_play_type() -> None:
    result = transform(sample(), 2023)
    assert result.skipped == {"null_play_type": 10, "no_play": 35}
    assert len(result.plays) == 309
    assert "no_play" not in set(result.plays["play_type"])
    assert sorted(result.games["external_game_id"]) == ["2023_01_ARI_WAS", "2023_01_DET_KC"]


def test_transform_converts_types_and_keeps_nulls() -> None:
    plays = transform(sample(), 2023).plays
    assert str(plays["down"].dtype) == "Int64"
    assert str(plays["touchdown"].dtype) == "boolean"
    kickoffs = plays[plays["play_type"] == "kickoff"]
    assert kickoffs["down"].isna().all()
    assert set(plays.columns) >= {"external_play_id", "is_pass", "yard_line_100", "epa"}


def test_rejection_reasons_flag_each_problem() -> None:
    df = sample()
    df = df[df["play_type"] == "pass"].head(5).copy()
    idx = list(df.index)
    df.loc[idx[0], "game_id"] = None
    df.loc[idx[1], "season"] = 2022
    df.loc[idx[2], "defteam"] = "OAK"
    df.loc[idx[3], "qtr"] = 9
    reasons = rejection_reasons(df, 2023)
    assert list(reasons) == [
        "missing game_id",
        "season does not match 2023",
        "unknown team in defteam",
        "qtr out of range",
        "",
    ]


def test_rejection_reasons_flag_non_integer_values() -> None:
    df = sample()
    df = df[df["play_type"] == "run"].head(2).copy()
    df.loc[df.index[0], "yards_gained"] = 3.5
    assert list(rejection_reasons(df, 2023)) == ["non-integer yards_gained", ""]


def test_json_safe_converts_missing_and_numpy() -> None:
    assert json_safe(float("nan")) is None
    assert json_safe(pd.NA) is None
    assert json_safe(np.int64(4)) == 4
    assert isinstance(json_safe(np.float64(1.5)), float)
    assert json_safe("KC") == "KC"
