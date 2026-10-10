"""Season ingestion: checksum-idempotent, chunked upserts with quarantine.

Called by the CLI and by the Celery import task. All data for one import is written
in a single transaction (in chunked statements), so a failure, cancellation, or worker
crash leaves no partial import behind and a retry starts from a clean slate.
"""

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingest.columns import REQUIRED_COLUMNS
from app.ingest.source import SourceFile, download, fetch_pbp
from app.ingest.teams import TEAMS
from app.ingest.transform import TransformResult, to_records, transform
from app.models import Dataset, DatasetStatus, Game, Play, Player, RejectedRow, Team

log = logging.getLogger(__name__)

PLAY_UPDATE_EXCLUDE = {"id", "game_id", "external_play_id"}


class IngestError(RuntimeError):
    """An import failed. The original exception is available as ``__cause__``."""


# Called with (stage, done, total). May raise to abort the import (e.g. on cancellation);
# the transaction is rolled back and the exception is chained onto IngestError.
ProgressCallback = Callable[[str, int, int], None]


@dataclass
class IngestSummary:
    season: int
    sha256: str
    source_version: str | None
    status: str
    dataset_id: int
    row_count: int = 0
    stored: int = 0
    rejected: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    games: int = 0
    players: int = 0
    stale_plays_removed: int = 0
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def upsert_teams(session: Session) -> dict[str, int]:
    rows = [t._asdict() for t in TEAMS]
    stmt = insert(Team).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Team.abbreviation],
        set_={
            "name": stmt.excluded.name,
            "conference": stmt.excluded.conference,
            "division": stmt.excluded.division,
        },
    )
    session.execute(stmt)
    return {abbr: id_ for id_, abbr in session.execute(select(Team.id, Team.abbreviation))}


def upsert_games(session: Session, games: pd.DataFrame, team_ids: dict[str, int]) -> dict[str, int]:
    if games.empty:
        return {}
    rows = [
        {
            "external_game_id": r["external_game_id"],
            "season": r["season"],
            "season_type": r["season_type"],
            "week": r["week"],
            "game_date": r["game_date"],
            "home_team_id": team_ids[r["home_team"]],
            "away_team_id": team_ids[r["away_team"]],
        }
        for r in to_records(games)
    ]
    stmt = insert(Game)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Game.external_game_id],
        set_={c: stmt.excluded[c] for c in rows[0] if c != "external_game_id"},
    )
    session.execute(stmt, rows)
    ext_ids = list(games["external_game_id"])
    result = session.execute(
        select(Game.id, Game.external_game_id).where(Game.external_game_id.in_(ext_ids))
    )
    return {ext: id_ for id_, ext in result}


def load_player_directory(cache_dir: Path) -> pd.DataFrame | None:
    """Name/position lookup from the nflverse players release; None if unavailable."""
    try:
        path = download(get_settings().nflverse_players_url, cache_dir / "players.parquet")
        df = pd.read_parquet(path, columns=["gsis_id", "display_name", "position"])
    except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
        log.warning("players release unavailable, storing IDs without names: %s", exc)
        return None
    return df.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id").set_index("gsis_id")


def upsert_players(
    session: Session, external_ids: Iterable[str], directory: pd.DataFrame | None
) -> dict[str, int]:
    ids = sorted(set(external_ids))
    if not ids:
        return {}
    rows: list[dict[str, Any]] = []
    for ext in ids:
        name = position = None
        if directory is not None and ext in directory.index:
            info = directory.loc[ext]
            name = info["display_name"] if pd.notna(info["display_name"]) else None
            position = info["position"] if pd.notna(info["position"]) else None
        rows.append({"external_player_id": ext, "name": name, "position": position})
    stmt = insert(Player)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Player.external_player_id],
        set_={
            "name": stmt.excluded.name,
            "position": stmt.excluded.position,
        },
    )
    session.execute(stmt, rows)
    result = session.execute(
        select(Player.id, Player.external_player_id).where(Player.external_player_id.in_(ids))
    )
    return {ext: id_ for id_, ext in result}


def build_play_rows(
    result: TransformResult,
    dataset_id: int,
    team_ids: dict[str, int],
    game_ids: dict[str, int],
    player_ids: dict[str, int],
) -> list[dict[str, Any]]:
    rows = []
    for rec in to_records(result.plays):
        rec["dataset_id"] = dataset_id
        rec["game_id"] = game_ids[rec.pop("external_game_id")]
        off, dfn = rec.pop("offense_team"), rec.pop("defense_team")
        rec["offense_team_id"] = team_ids[off] if off else None
        rec["defense_team_id"] = team_ids[dfn] if dfn else None
        for role in ("passer", "rusher", "receiver"):
            ext = rec.pop(f"{role}_external_id")
            rec[f"{role}_player_id"] = player_ids[ext] if ext else None
        rows.append(rec)
    return rows


def upsert_plays(session: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    stmt = insert(Play)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_plays_game_id_external_play_id",
        set_={c: stmt.excluded[c] for c in rows[0] if c not in PLAY_UPDATE_EXCLUDE},
    )
    session.execute(stmt, rows)


def _start_dataset(session: Session, src: SourceFile, season: int) -> Dataset:
    dataset = session.scalar(select(Dataset).where(Dataset.sha256 == src.sha256))
    if dataset is None:
        dataset = Dataset(
            source_url=src.url,
            source_version=src.version,
            sha256=src.sha256,
            season=season,
            status=DatasetStatus.RUNNING,
        )
        session.add(dataset)
    else:
        dataset.status = DatasetStatus.RUNNING
        dataset.error = None
        dataset.source_version = src.version
        session.execute(delete(RejectedRow).where(RejectedRow.dataset_id == dataset.id))
    session.flush()
    return dataset


def ingest_season(
    session: Session,
    season: int,
    *,
    source: SourceFile | None = None,
    cache_dir: Path | None = None,
    chunk_size: int | None = None,
    force: bool = False,
    player_directory: pd.DataFrame | None = None,
    progress: ProgressCallback | None = None,
) -> IngestSummary:
    """Import one season. Skips the file if a completed dataset has the same SHA-256."""

    def report(stage: str, done: int, total: int) -> None:
        if progress is not None:
            progress(stage, done, total)

    started = time.monotonic()
    settings = get_settings()
    cache = cache_dir or settings.data_cache_dir
    chunk = chunk_size or settings.ingest_chunk_size
    src = source or fetch_pbp(season, cache)

    existing = session.scalar(select(Dataset).where(Dataset.sha256 == src.sha256))
    if existing is not None and existing.status == DatasetStatus.COMPLETED and not force:
        log.info("season %s: sha256 %s already imported, skipping", season, src.sha256[:12])
        return IngestSummary(
            season=season,
            sha256=src.sha256,
            source_version=existing.source_version,
            status="skipped_duplicate",
            dataset_id=existing.id,
            row_count=existing.row_count or 0,
            stored=existing.stored_count or 0,
            rejected=existing.rejected_count or 0,
        )

    dataset = _start_dataset(session, src, season)
    session.commit()
    dataset_id = dataset.id
    try:
        raw = pd.read_parquet(src.path, columns=REQUIRED_COLUMNS)
        result = transform(raw, season)
        team_ids = upsert_teams(session)
        game_ids = upsert_games(session, result.games, team_ids)

        player_ext: set[str] = set()
        for role in ("passer", "rusher", "receiver"):
            player_ext |= set(result.plays[f"{role}_external_id"].dropna())
        directory = player_directory
        if directory is None and player_ext:
            directory = load_player_directory(cache)
        player_ids = upsert_players(session, player_ext, directory)
        session.flush()

        rows = build_play_rows(result, dataset_id, team_ids, game_ids, player_ids)
        report("plays", 0, len(rows))
        for start in range(0, len(rows), chunk):
            upsert_plays(session, rows[start : start + chunk])
            done = min(start + chunk, len(rows))
            log.info("season %s: upserted %s/%s plays", season, done, len(rows))
            report("plays", done, len(rows))

        if result.rejected:
            session.execute(
                insert(RejectedRow),
                [
                    {
                        "dataset_id": dataset_id,
                        "source_row_ref": r.source_row_ref,
                        "reason": r.reason,
                        "raw_json": r.raw,
                    }
                    for r in result.rejected
                ],
            )

        # The new file is the full season; plays it no longer contains are stale.
        stale_result: CursorResult[Any] = session.execute(  # type: ignore[assignment]
            delete(Play).where(Play.season == season, Play.dataset_id != dataset_id)
        )
        stale = stale_result.rowcount

        dataset = session.get_one(Dataset, dataset_id)
        dataset.row_count = len(raw)
        dataset.stored_count = len(rows)
        dataset.skipped_count = sum(result.skipped.values())
        dataset.rejected_count = len(result.rejected)
        dataset.status = DatasetStatus.COMPLETED
        dataset.completed_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        session.rollback()
        failed = session.get_one(Dataset, dataset_id)
        failed.status = DatasetStatus.FAILED
        failed.error = f"{type(exc).__name__}: {exc}"[:2000]
        session.commit()
        raise IngestError(f"season {season} import failed: {exc}") from exc

    return IngestSummary(
        season=season,
        sha256=src.sha256,
        source_version=src.version,
        status="imported",
        dataset_id=dataset_id,
        row_count=len(raw),
        stored=len(rows),
        rejected=len(result.rejected),
        skipped=result.skipped,
        games=len(game_ids),
        players=len(player_ids),
        stale_plays_removed=int(stale or 0),
        seconds=round(time.monotonic() - started, 2),
    )
