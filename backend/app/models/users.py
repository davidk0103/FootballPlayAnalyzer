from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lowercased; uniqueness is therefore case-insensitive.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    # Exactly one of password_hash / external_auth_id is expected; external auth is a
    # reserved column for a future identity provider and is unused today.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    external_auth_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_admin: Mapped[bool] = mapped_column(default=False)
    # Embedded in every session token; bumping it revokes all of the user's sessions.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiUsage(Base):
    """One row per authenticated request to a private endpoint (audit trail, not billing)."""

    __tablename__ = "api_usage"
    __table_args__ = (Index(None, "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
