"""users, api_usage, and import_jobs -> jobs (owned, multi task type)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-11 10:00:00.000000

The table rename keeps every existing job row. Constraint and index names follow the
project naming convention, so they are renamed explicitly; otherwise ``alembic check``
would report drift between the models and the database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = sa.text("status IN ('queued', 'running', 'retrying', 'cancel_requested')")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("external_auth_id", sa.String(length=255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("external_auth_id", name=op.f("uq_users_external_auth_id")),
    )
    op.create_table(
        "api_usage",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=200), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_usage_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_usage")),
    )
    op.create_index(op.f("ix_api_usage_user_id_created_at"), "api_usage", ["user_id", "created_at"])

    op.rename_table("import_jobs", "jobs")
    op.execute("ALTER TABLE jobs RENAME CONSTRAINT pk_import_jobs TO pk_jobs")
    op.execute(
        "ALTER TABLE jobs RENAME CONSTRAINT uq_import_jobs_idempotency_key"
        " TO uq_jobs_idempotency_key"
    )
    op.execute("ALTER INDEX ix_import_jobs_status_created_at RENAME TO ix_jobs_status_created_at")
    op.execute("ALTER INDEX uq_import_jobs_active_target RENAME TO uq_jobs_active_target")
    op.execute(
        "ALTER TABLE job_attempts RENAME CONSTRAINT fk_job_attempts_job_id_import_jobs"
        " TO fk_job_attempts_job_id_jobs"
    )
    # Pre-auth jobs have user_id NULL (no users existed), so the new FK cannot fail.
    op.create_foreign_key(
        op.f("fk_jobs_user_id_users"), "jobs", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(op.f("ix_jobs_user_id"), "jobs", ["user_id"])
    op.add_column("jobs", sa.Column("progress", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "progress")
    op.drop_index(op.f("ix_jobs_user_id"), table_name="jobs")
    op.drop_constraint(op.f("fk_jobs_user_id_users"), "jobs", type_="foreignkey")
    op.execute(
        "ALTER TABLE job_attempts RENAME CONSTRAINT fk_job_attempts_job_id_jobs"
        " TO fk_job_attempts_job_id_import_jobs"
    )
    op.execute("ALTER INDEX uq_jobs_active_target RENAME TO uq_import_jobs_active_target")
    op.execute("ALTER INDEX ix_jobs_status_created_at RENAME TO ix_import_jobs_status_created_at")
    op.execute(
        "ALTER TABLE jobs RENAME CONSTRAINT uq_jobs_idempotency_key"
        " TO uq_import_jobs_idempotency_key"
    )
    op.execute("ALTER TABLE jobs RENAME CONSTRAINT pk_jobs TO pk_import_jobs")
    op.rename_table("jobs", "import_jobs")

    op.drop_index(op.f("ix_api_usage_user_id_created_at"), table_name="api_usage")
    op.drop_table("api_usage")
    op.drop_table("users")
