import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.jobs.state import AttemptStatus, JobStatus
from app.models.base import Base

ACTIVE_STATUSES_SQL = "('queued', 'running', 'retrying', 'cancel_requested')"


def _values(e: type[JobStatus] | type[AttemptStatus]) -> list[str]:
    return [m.value for m in e]


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index(None, "status", "created_at"),
        # Duplicate-submission protection: at most one active job per (task_type, target).
        Index(
            "uq_jobs_active_target",
            "task_type",
            "target_key",
            unique=True,
            postgresql_where=text(f"status IN {ACTIVE_STATUSES_SQL}"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Who submitted it. Season imports are public (visible to everyone) but still record
    # the admin who started them; other task types are private to this user.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    task_type: Mapped[str] = mapped_column(String(50))
    # What the job acts on (e.g. "season:2024", "upload:<uuid>"); scopes duplicate protection.
    target_key: Mapped[str] = mapped_column(String(100))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", values_callable=_values)
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    result_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Latest checkpoint of the running attempt: {"stage": ..., "done": n, "total": n}.
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    celery_task_id: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status", values_callable=_values)
    )
    worker: Mapped[str | None] = mapped_column(String(200))
    error_type: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    retry_delay_seconds: Mapped[float | None]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
