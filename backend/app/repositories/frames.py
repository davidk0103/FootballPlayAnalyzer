"""Load public play-by-play into the standard analytics frame.

A season is ~45k rows, which pandas handles in milliseconds once loaded; the database
round trip dominates. Loaded frames are kept in a small per-process LRU keyed by the
dataset checksum, so a re-import (new checksum) can never serve stale rows.
"""

import threading
import uuid
from collections import OrderedDict

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.analytics.frame import BOOL_COLUMNS, INT_COLUMNS, coerce_frame
from app.models import Game, Play, Player, Team, UserPlay

MAX_CACHED_SEASONS = 6
MAX_CACHED_UPLOADS = 8

_lock = threading.Lock()
_frames: OrderedDict[tuple[int, str], pd.DataFrame] = OrderedDict()
_upload_frames: OrderedDict[tuple[uuid.UUID, str], pd.DataFrame] = OrderedDict()


def _query_season(session: Session, season: int) -> pd.DataFrame:
    off, de = aliased(Team), aliased(Team)
    passer, rusher, receiver = aliased(Player), aliased(Player), aliased(Player)
    direct = [getattr(Play, c) for c in INT_COLUMNS + BOOL_COLUMNS if hasattr(Play, c)]
    stmt = (
        select(
            Game.external_game_id.label("game_key"),
            Play.season_type,
            Play.play_type,
            off.abbreviation.label("offense"),
            de.abbreviation.label("defense"),
            passer.external_player_id.label("passer_id"),
            rusher.external_player_id.label("rusher_id"),
            receiver.external_player_id.label("receiver_id"),
            Play.epa,
            *direct,
        )
        .join(Game, Game.id == Play.game_id)
        .outerjoin(off, off.id == Play.offense_team_id)
        .outerjoin(de, de.id == Play.defense_team_id)
        .outerjoin(passer, passer.id == Play.passer_player_id)
        .outerjoin(rusher, rusher.id == Play.rusher_player_id)
        .outerjoin(receiver, receiver.id == Play.receiver_player_id)
        .where(Play.season == season)
        .order_by(Play.game_id, Play.external_play_id)
    )
    result = session.execute(stmt)
    return pd.DataFrame(result.all(), columns=list(result.keys()))


def public_season_frame(session: Session, season: int, dataset_sha: str) -> pd.DataFrame:
    """Every stored play of a season (all play types) as a standard frame. Read-only."""
    key = (season, dataset_sha)
    with _lock:
        cached = _frames.get(key)
        if cached is not None:
            _frames.move_to_end(key)
            return cached
    frame = coerce_frame(_query_season(session, season))
    with _lock:
        for stale in [k for k in _frames if k[0] == season]:
            del _frames[stale]
        _frames[key] = frame
        while len(_frames) > MAX_CACHED_SEASONS:
            _frames.popitem(last=False)
    return frame


def _query_upload(session: Session, dataset_id: uuid.UUID) -> pd.DataFrame:
    columns = [c for c in UserPlay.__table__.columns if c.name not in ("id", "dataset_id")]
    result = session.execute(
        select(*columns).where(UserPlay.dataset_id == dataset_id).order_by(UserPlay.row_number)
    )
    return pd.DataFrame(result.all(), columns=list(result.keys()))


def upload_frame(session: Session, dataset_id: uuid.UUID, version: str) -> pd.DataFrame:
    """A processed upload as a standard frame. Uploads never mix with public seasons.

    Uploads carry no player ids or official yardage columns, so those stay unknown;
    ``play_deleted`` is derived from ``play_type == "no_play"``.
    """
    key = (dataset_id, version)
    with _lock:
        cached = _upload_frames.get(key)
        if cached is not None:
            _upload_frames.move_to_end(key)
            return cached
    raw = _query_upload(session, dataset_id)
    frame = coerce_frame(raw)
    frame["play_deleted"] = (frame["play_type"] == "no_play").astype("boolean")
    with _lock:
        _upload_frames[key] = frame
        while len(_upload_frames) > MAX_CACHED_UPLOADS:
            _upload_frames.popitem(last=False)
    return frame


def clear_upload_frames(dataset_id: uuid.UUID) -> None:
    with _lock:
        for stale in [k for k in _upload_frames if k[0] == dataset_id]:
            del _upload_frames[stale]


def clear_frame_cache() -> None:
    with _lock:
        _frames.clear()
        _upload_frames.clear()
