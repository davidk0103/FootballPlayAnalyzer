"""Resolve which plays an analytics request runs on: a public season or a private upload.

Public seasons come from the shared nflverse tables. Uploaded datasets live in separate
tables and are only visible to their owner; any other caller gets 404, exactly as if
the dataset did not exist.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.filters import PlayFilters
from app.analytics.frame import team_view
from app.models import Dataset, User, UserDataset, UserPlay
from app.repositories import plays as plays_repo
from app.repositories.frames import public_season_frame, upload_frame
from app.schemas import DatasetOut, TeamKey
from app.services.catalog import require_team
from app.services.errors import InvalidRequestError, NotFoundError

PUBLIC_SOURCE = "nflverse pbp"
UPLOAD_SOURCE = "user upload"


@dataclass
class PlaySource:
    load: Callable[[], pd.DataFrame]
    dataset: DatasetOut
    # Cache scoping: public seasons use the season generation counter; uploads use 0
    # plus their own id/checksum (their content never changes after processing).
    cache_season: int
    cache_sha: str
    cache_scope: str
    public: bool
    team_names: dict[str, str | None]
    _frame: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def frame(self) -> pd.DataFrame:
        """Loaded on first use, so cache hits never touch the play tables."""
        if self._frame is None:
            self._frame = self.load()
        return self._frame

    def require_team(self, session: Session, key: str) -> TeamKey:
        if self.public:
            team = require_team(session, key)
            return TeamKey(abbreviation=team.abbreviation, name=team.name)
        abbr = key.strip().upper()
        if abbr not in self.team_names:
            raise NotFoundError(f"Team '{key}' not found in this dataset")
        return TeamKey(abbreviation=abbr, name=self.team_names[abbr])

    def view(self, filters: PlayFilters, team: str | None) -> pd.DataFrame:
        """Season-scoped team_view for ``team`` (or the league when None)."""
        frame = self.frame
        if not self.public and filters.season is not None:
            frame = frame[(frame["season"] == filters.season).fillna(False)]
        return team_view(frame, team, filters.side)


def public_source(session: Session, season: int | None) -> PlaySource:
    if season is None:
        raise InvalidRequestError("season is required for public data")
    dataset = plays_repo.latest_dataset(session, season)
    if dataset is None:
        raise NotFoundError(f"No imported data for season {season}")
    return _public(session, dataset)


def _public(session: Session, dataset: Dataset) -> PlaySource:
    return PlaySource(
        load=lambda: public_season_frame(session, dataset.season, dataset.sha256),
        dataset=DatasetOut(
            source=PUBLIC_SOURCE, version=dataset.source_version, sha256=dataset.sha256
        ),
        cache_season=dataset.season,
        cache_sha=dataset.sha256,
        cache_scope="public",
        public=True,
        team_names={},
    )


def upload_source(session: Session, dataset_id: uuid.UUID, viewer: User | None) -> PlaySource:
    from app.uploads.service import get_ready_upload

    dataset: UserDataset = get_ready_upload(session, dataset_id, viewer)
    version = dataset.content_version or dataset.sha256
    owned = UserPlay.dataset_id == dataset.id
    offenses = session.scalars(select(UserPlay.offense).where(owned).distinct())
    defenses = session.scalars(select(UserPlay.defense).where(owned).distinct())
    teams = sorted(set(offenses) | set(defenses))
    return PlaySource(
        load=lambda: upload_frame(session, dataset.id, version),
        dataset=DatasetOut(
            source=UPLOAD_SOURCE,
            version=dataset.processed_at.isoformat() if dataset.processed_at else None,
            sha256=dataset.sha256,
            kind="upload",
            id=str(dataset.id),
            name=dataset.name,
        ),
        cache_season=0,
        cache_sha=version,
        cache_scope=f"upload:{dataset.id}",
        public=False,
        team_names={t: None for t in teams},
    )


def resolve_source(
    session: Session, season: int | None, dataset_id: uuid.UUID | None, viewer: User | None
) -> PlaySource:
    """An owned upload when ``dataset_id`` is given, else the public season."""
    if dataset_id is not None:
        return upload_source(session, dataset_id, viewer)
    return public_source(session, season)
