"""Resolve which plays an analytics request runs on: a public season or a private upload.

Public seasons come from the shared nflverse tables. Uploaded datasets live in separate
tables and are only visible to their owner; any other caller gets 404, exactly as if
the dataset did not exist.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy.orm import Session

from app.analytics.filters import PlayFilters
from app.analytics.frame import team_view
from app.models import Dataset
from app.repositories import plays as plays_repo
from app.repositories.frames import public_season_frame
from app.schemas import DatasetOut, TeamKey
from app.services.catalog import require_team
from app.services.errors import InvalidRequestError, NotFoundError

PUBLIC_SOURCE = "nflverse pbp"


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
