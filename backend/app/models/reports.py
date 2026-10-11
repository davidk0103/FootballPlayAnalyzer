"""Saved scouting reports and their generated export files (owned by one user)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReportStatus(enum.StrEnum):
    PENDING = "pending"  # a generate_report job is building report_json
    READY = "ready"
    FAILED = "failed"


class ExportFormat(enum.StrEnum):
    CSV = "csv"
    JSON = "json"


def _enum[E: enum.Enum](cls: type[E], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class SavedReport(Base):
    __tablename__ = "saved_reports"
    __table_args__ = (Index(None, "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    team: Mapped[str] = mapped_column(String(5))
    season: Mapped[int | None] = mapped_column(SmallInteger)
    # A report on an upload keeps its snapshot if the upload is later deleted.
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_datasets.id", ondelete="SET NULL"), index=True
    )
    filters_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[ReportStatus] = mapped_column(_enum(ReportStatus, "report_status"))
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReportExport(Base):
    __tablename__ = "report_exports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("saved_reports.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[ExportFormat] = mapped_column(_enum(ExportFormat, "export_format"))
    status: Mapped[ReportStatus] = mapped_column(_enum(ReportStatus, "report_status"))
    storage_key: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
