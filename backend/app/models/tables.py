import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DatasetStatus(enum.StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(String(500))
    source_version: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    season: Mapped[int] = mapped_column(SmallInteger, index=True)
    row_count: Mapped[int | None] = mapped_column(Integer)
    stored_count: Mapped[int | None] = mapped_column(Integer)
    skipped_count: Mapped[int | None] = mapped_column(Integer)
    rejected_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[DatasetStatus] = mapped_column(
        Enum(DatasetStatus, name="dataset_status", values_callable=lambda e: [m.value for m in e])
    )
    error: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    abbreviation: Mapped[str] = mapped_column(String(5), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    conference: Mapped[str] = mapped_column(String(3))
    division: Mapped[str] = mapped_column(String(10))


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_player_id: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str | None] = mapped_column(String(120))
    position: Mapped[str | None] = mapped_column(String(10))


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (Index(None, "season", "week"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_game_id: Mapped[str] = mapped_column(String(30), unique=True)
    season: Mapped[int] = mapped_column(SmallInteger)
    season_type: Mapped[str] = mapped_column(String(4))
    week: Mapped[int] = mapped_column(SmallInteger)
    game_date: Mapped[date | None] = mapped_column(Date)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id], lazy="joined")
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id], lazy="joined")


class Play(Base):
    """One stored nflverse play. Indicator columns are nullable: NULL means unknown, never 0."""

    __tablename__ = "plays"
    __table_args__ = (
        UniqueConstraint("game_id", "external_play_id"),
        Index(None, "season", "offense_team_id"),
        Index(None, "season", "defense_team_id"),
        Index(None, "game_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    external_play_id: Mapped[int] = mapped_column(Integer)
    offense_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    defense_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    # Copied from games so the common season/week filters avoid a join.
    season: Mapped[int] = mapped_column(SmallInteger)
    season_type: Mapped[str] = mapped_column(String(4))
    week: Mapped[int] = mapped_column(SmallInteger)

    qtr: Mapped[int | None] = mapped_column(SmallInteger)
    game_seconds_remaining: Mapped[int | None] = mapped_column(Integer)
    down: Mapped[int | None] = mapped_column(SmallInteger)
    yards_to_go: Mapped[int | None] = mapped_column(SmallInteger)
    yard_line_100: Mapped[int | None] = mapped_column(SmallInteger)
    score_differential: Mapped[int | None] = mapped_column(SmallInteger)

    play_type: Mapped[str] = mapped_column(String(20))
    yards_gained: Mapped[int | None] = mapped_column(SmallInteger)
    epa: Mapped[float | None] = mapped_column(Float)
    success: Mapped[bool | None]

    is_pass: Mapped[bool | None]
    is_rush: Mapped[bool | None]
    complete_pass: Mapped[bool | None]
    sack: Mapped[bool | None]
    qb_scramble: Mapped[bool | None]
    touchdown: Mapped[bool | None]
    interception: Mapped[bool | None]
    fumble_lost: Mapped[bool | None]
    first_down: Mapped[bool | None]
    first_down_penalty: Mapped[bool | None]
    penalty: Mapped[bool | None]
    third_down_converted: Mapped[bool | None]
    third_down_failed: Mapped[bool | None]
    fourth_down_converted: Mapped[bool | None]
    two_point_attempt: Mapped[bool | None]
    aborted_play: Mapped[bool | None]
    play_deleted: Mapped[bool | None]

    passer_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    rusher_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    receiver_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))


class RejectedRow(Base):
    __tablename__ = "rejected_rows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    source_row_ref: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(String(200))
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
