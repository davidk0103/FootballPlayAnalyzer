"""Private, user-uploaded datasets. Kept in their own tables so uploaded rows can never
leak into public nflverse analytics, and deleted wholesale with their dataset."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UploadStatus(enum.StrEnum):
    UPLOADED = "uploaded"  # file stored and parsed; no mapping confirmed yet
    VALIDATED = "validated"  # mapping checked against a sample of rows
    PROCESSING = "processing"  # an import_upload job owns the dataset
    READY = "ready"  # rows stored; analytics available
    FAILED = "failed"


class UserDataset(Base):
    __tablename__ = "user_datasets"
    __table_args__ = (Index(None, "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    original_filename: Mapped[str] = mapped_column(String(255))
    # Random storage name; NULL once the file is deleted after successful processing.
    storage_key: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    delimiter: Mapped[str] = mapped_column(String(1))
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status", values_callable=lambda e: [m.value for m in e])
    )
    columns: Mapped[list[str]] = mapped_column(JSONB)
    preview: Mapped[list[list[str]]] = mapped_column(JSONB)
    mapping: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    # Checksum of file + mapping used for the stored rows; scopes analytics cache keys.
    content_version: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    stored_count: Mapped[int | None] = mapped_column(Integer)
    rejected_count: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserPlay(Base):
    """One uploaded play, already normalized to the standard schema."""

    __tablename__ = "user_plays"
    __table_args__ = (Index(None, "dataset_id", "offense"), Index(None, "dataset_id", "defense"))

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_datasets.id", ondelete="CASCADE")
    )
    row_number: Mapped[int] = mapped_column(Integer)
    game_key: Mapped[str] = mapped_column(String(60))
    season: Mapped[int | None] = mapped_column(SmallInteger)
    season_type: Mapped[str | None] = mapped_column(String(4))
    week: Mapped[int | None] = mapped_column(SmallInteger)
    offense: Mapped[str] = mapped_column(String(5))
    defense: Mapped[str] = mapped_column(String(5))
    qtr: Mapped[int | None] = mapped_column(SmallInteger)
    down: Mapped[int | None] = mapped_column(SmallInteger)
    yards_to_go: Mapped[int | None] = mapped_column(SmallInteger)
    yard_line_100: Mapped[int | None] = mapped_column(SmallInteger)
    score_differential: Mapped[int | None] = mapped_column(SmallInteger)
    play_type: Mapped[str] = mapped_column(String(20))
    yards_gained: Mapped[int | None] = mapped_column(SmallInteger)
    epa: Mapped[float | None] = mapped_column(Float)
    success: Mapped[bool | None]
    complete_pass: Mapped[bool | None]
    sack: Mapped[bool | None]
    touchdown: Mapped[bool | None]
    interception: Mapped[bool | None]
    fumble_lost: Mapped[bool | None]
    first_down: Mapped[bool | None]
    first_down_penalty: Mapped[bool | None]
    penalty: Mapped[bool | None]
    third_down_converted: Mapped[bool | None]
    two_point_attempt: Mapped[bool | None]


class UserRejectedRow(Base):
    __tablename__ = "user_rejected_rows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_datasets.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(300))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
