import io
from pathlib import Path

import pandas as pd
import pytest

from app.storage import FileTooLargeError, LocalStorage
from app.uploads.csvfile import CsvValidationError, inspect_csv, read_frame
from app.uploads.mapping import mapping_errors, suggest_mapping
from app.uploads.normalize import normalize

LIMITS = {"max_columns": 10, "max_rows": 100, "preview_rows": 2}
BASE_MAPPING = {"game_key": "g", "offense": "o", "defense": "d", "play_type": "t"}


def inspect(content: bytes, **overrides: int) -> object:
    return inspect_csv(io.BytesIO(content), **{**LIMITS, **overrides})


def frame(rows: list[dict[str, str]]) -> pd.DataFrame:
    buf = io.BytesIO(pd.DataFrame(rows).to_csv(index=False).encode())
    return read_frame(buf, ",")


def test_inspect_detects_delimiter_bom_and_skips_blank_lines() -> None:
    info = inspect_csv(
        io.BytesIO("\ufeffgame;team\r\nG1;DET\r\n\r\n;\r\nG2;KC\r\n".encode()), **LIMITS
    )
    assert info.delimiter == ";"
    assert info.columns == ["game", "team"]
    assert info.row_count == 2
    assert info.preview == [["G1", "DET"], ["G2", "KC"]]


@pytest.mark.parametrize(
    ("content", "limits", "code"),
    [
        (b"a,b\n" + b"1,2\n" * 101, {}, "too_many_rows"),
        (
            b",".join(f"c{i}".encode() for i in range(11)) + b"\n" + b"1," * 10 + b"1\n",
            {},
            "too_many_columns",
        ),
        (b"a,\n1,2\n", {}, "bad_header"),
        (b"a,A\n1,2\n", {}, "bad_header"),
        (b'a,b\n"unterminated,2\n', {}, "malformed_csv"),
        (b"a,b\n" + b"x" * 1001 + b",1\n", {}, "cell_too_long"),
    ],
)
def test_inspect_rejects(content: bytes, limits: dict[str, int], code: str) -> None:
    with pytest.raises(CsvValidationError) as err:
        inspect(content, **limits)
    assert err.value.code == code


def test_inspect_leaves_stream_open() -> None:
    stream = io.BytesIO(b"a,b\n1,2\n")
    inspect_csv(stream, **LIMITS)
    stream.seek(0)
    assert stream.read() == b"a,b\n1,2\n"


def test_suggest_mapping_matches_aliases_once() -> None:
    columns = ["Game_ID", "posteam", "DefTeam", "Play Type", "ydstogo", "Yards", "EPA", "notes"]
    assert suggest_mapping(columns) == {
        "game_key": "Game_ID",
        "offense": "posteam",
        "defense": "DefTeam",
        "play_type": "Play Type",
        "yards_to_go": "ydstogo",
        "yards_gained": "Yards",
        "epa": "EPA",
    }


def test_mapping_errors() -> None:
    columns = ["g", "o", "d", "t"]
    assert mapping_errors(BASE_MAPPING, columns) == []
    errors = mapping_errors({"game_key": "g", "offense": "g", "bogus": "o"}, columns)
    assert "Unknown field 'bogus'" in errors
    assert "Defense is required; map a column to it" in errors
    assert "Column 'g' is mapped to both Game ID and Offense" in errors


def test_normalize_parses_types_and_synonyms() -> None:
    raw = frame(
        [
            {
                "g": "G1",
                "o": "det",
                "d": "KC",
                "t": "Rush",
                "dn": "3",
                "ytg": "4.0",
                "td": "Yes",
                "epa": "0.25",
                "fd": "1",
            },
            {
                "g": "G1",
                "o": "DET",
                "d": "KC",
                "t": "FG",
                "dn": "",
                "ytg": "",
                "td": "",
                "epa": "",
                "fd": "",
            },
        ]
    )
    mapping = {
        **BASE_MAPPING,
        "down": "dn",
        "yards_to_go": "ytg",
        "touchdown": "td",
        "epa": "epa",
        "first_down": "fd",
    }
    out = normalize(raw, mapping)
    assert out.rejected.empty
    first, second = out.plays.iloc[0], out.plays.iloc[1]
    assert (first["offense"], first["play_type"], first["down"], first["yards_to_go"]) == (
        "DET",
        "run",
        3,
        4,
    )
    assert bool(first["touchdown"])
    assert bool(first["success"]) and bool(first["third_down_converted"])
    assert second["play_type"] == "field_goal"
    assert pd.isna(second["down"]) and pd.isna(second["touchdown"]) and pd.isna(second["success"])
    assert any("derived from EPA" in w for w in out.warnings)
    assert any("Third-down conversions were derived" in w for w in out.warnings)


def test_normalize_rejects_with_row_specific_reasons() -> None:
    raw = frame(
        [
            {"g": "G1", "o": "DET", "d": "KC", "t": "pass", "dn": "5"},
            {"g": "", "o": "TOOLONGNAME", "d": "KC", "t": "pass", "dn": "1.5"},
            {"g": "G1", "o": "KC", "d": "KC", "t": "pass", "dn": "2"},
            {"g": "G1", "o": "DET", "d": "KC", "t": "pass", "dn": "2"},
        ]
    )
    out = normalize(raw, {**BASE_MAPPING, "down": "dn"})
    reasons = dict(zip(out.rejected["row_number"], out.rejected["reason"], strict=True))
    assert reasons[1] == "Down must be a whole number from 1 to 4 (got '5')"
    assert reasons[2] == (
        "Game ID is blank; Offense must be a 1-5 character team code (got 'TOOLONGNAME'); "
        "Down must be a whole number from 1 to 4 (got '1.5')"
    )
    assert reasons[3] == "Offense and defense are the same team"
    assert list(out.plays["row_number"]) == [4]


def test_normalize_keeps_formula_like_text_as_data() -> None:
    raw = frame([{"g": "=1+1", "o": "DET", "d": "KC", "t": "pass"}])
    out = normalize(raw, BASE_MAPPING)
    assert out.plays.iloc[0]["game_key"] == "=1+1"


def test_storage_random_names_limit_and_key_validation(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    key, size = storage.save("uploads", io.BytesIO(b"abc"), suffix=".csv", max_bytes=10)
    assert key.startswith("uploads/") and key.endswith(".csv") and size == 3
    assert storage.exists(key)
    with pytest.raises(FileTooLargeError):
        storage.save("uploads", io.BytesIO(b"x" * 11), suffix=".csv", max_bytes=10)
    assert len(list((tmp_path / "uploads").iterdir())) == 1  # partial file removed
    for bad in ("../etc/passwd", "uploads/../../x", "other/file", "uploads/.hidden", "uploads/"):
        with pytest.raises(ValueError):
            storage.open(bad)
    storage.delete(key)
    assert not storage.exists(key)
