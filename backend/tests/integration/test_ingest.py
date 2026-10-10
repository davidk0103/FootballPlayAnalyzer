from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingest.service import IngestError
from app.ingest.source import SourceFile
from app.models import Dataset, DatasetStatus, Game, Play, Player, RejectedRow, Team
from tests.conftest import PBP_SAMPLE
from tests.integration.conftest import ingest_fixture

pytestmark = pytest.mark.integration

# 354 raw rows: 35 no_play, 10 with null play_type -> 309 stored.
RAW_ROWS = 354
STORED = 309


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_ingest_fixture_stores_expected_rows(
    db_session: Session, player_directory: pd.DataFrame
) -> None:
    summary = ingest_fixture(db_session, player_directory, chunk_size=100)

    assert summary.status == "imported"
    assert summary.row_count == RAW_ROWS
    assert summary.skipped == {"null_play_type": 10, "no_play": 35}
    assert summary.stored == STORED
    assert summary.rejected == 0
    assert summary.games == 2
    assert count(db_session, Play) == STORED
    assert count(db_session, Game) == 2
    assert count(db_session, Team) == 32

    dataset = db_session.get_one(Dataset, summary.dataset_id)
    assert dataset.status == DatasetStatus.COMPLETED
    assert (dataset.row_count, dataset.stored_count, dataset.skipped_count) == (354, 309, 45)

    goff = db_session.scalar(select(Player).where(Player.name == "Jared Goff"))
    assert goff is not None and goff.position == "QB"


def test_reimport_same_checksum_is_skipped(
    db_session: Session, player_directory: pd.DataFrame
) -> None:
    first = ingest_fixture(db_session, player_directory)
    second = ingest_fixture(db_session, player_directory)

    assert second.status == "skipped_duplicate"
    assert second.dataset_id == first.dataset_id
    assert count(db_session, Play) == STORED
    assert count(db_session, Dataset) == 1


def test_forced_reimport_upserts_without_duplicates(
    db_session: Session, player_directory: pd.DataFrame
) -> None:
    ingest_fixture(db_session, player_directory)
    again = ingest_fixture(db_session, player_directory, force=True)

    assert again.status == "imported"
    assert count(db_session, Play) == STORED
    assert count(db_session, Dataset) == 1


def test_invalid_rows_are_quarantined(
    db_session: Session, player_directory: pd.DataFrame, tmp_path: Path
) -> None:
    raw = pd.read_parquet(PBP_SAMPLE)
    passes = raw.index[raw["play_type"] == "pass"]
    raw.loc[passes[0], "posteam"] = "XYZ"
    raw.loc[passes[1], "down"] = 7
    raw = pd.concat([raw, raw.loc[[passes[2]]]], ignore_index=True)
    path = tmp_path / "bad.parquet"
    raw.to_parquet(path, index=False)

    summary = ingest_fixture(db_session, player_directory, path=path)

    assert summary.rejected == 3
    assert summary.stored == STORED - 2
    reasons = set(db_session.scalars(select(RejectedRow.reason)))
    assert reasons == {
        "unknown team in posteam",
        "down out of range",
        "duplicate (game_id, play_id)",
    }
    rejected = db_session.scalar(
        select(RejectedRow).where(RejectedRow.reason == "unknown team in posteam")
    )
    assert rejected is not None and rejected.raw_json["posteam"] == "XYZ"


def test_missing_values_stay_null(
    db_session: Session, player_directory: pd.DataFrame, tmp_path: Path
) -> None:
    raw = pd.read_parquet(PBP_SAMPLE)
    target = raw.index[raw["play_type"] == "run"][0]
    play_id = int(raw.loc[target, "play_id"])
    raw.loc[target, ["epa", "success", "touchdown"]] = float("nan")
    path = tmp_path / "nulls.parquet"
    raw.to_parquet(path, index=False)

    ingest_fixture(db_session, player_directory, path=path)

    play = db_session.scalar(select(Play).where(Play.external_play_id == play_id))
    assert play is not None
    assert play.epa is None
    assert play.success is None
    assert play.touchdown is None


def test_new_file_version_replaces_stale_plays(
    db_session: Session, player_directory: pd.DataFrame, tmp_path: Path
) -> None:
    first = ingest_fixture(db_session, player_directory)
    raw = pd.read_parquet(PBP_SAMPLE)
    trimmed = raw[raw["game_id"] == "2023_01_DET_KC"]
    path = tmp_path / "v2.parquet"
    trimmed.to_parquet(path, index=False)

    second = ingest_fixture(db_session, player_directory, path=path)

    assert second.dataset_id != first.dataset_id
    assert second.stale_plays_removed == STORED - second.stored
    dataset_ids = set(db_session.scalars(select(Play.dataset_id).distinct()))
    assert dataset_ids == {second.dataset_id}


def test_failed_import_marks_dataset_failed(
    db_session: Session, player_directory: pd.DataFrame, tmp_path: Path
) -> None:
    missing = tmp_path / "missing.parquet"
    source = SourceFile(url="file://missing", path=missing, sha256="f" * 64, version=None)
    from app.ingest.service import ingest_season

    with pytest.raises(IngestError):
        ingest_season(db_session, 2023, source=source, player_directory=player_directory)

    dataset = db_session.scalar(select(Dataset).where(Dataset.sha256 == "f" * 64))
    assert dataset is not None
    assert dataset.status == DatasetStatus.FAILED
    assert dataset.error
