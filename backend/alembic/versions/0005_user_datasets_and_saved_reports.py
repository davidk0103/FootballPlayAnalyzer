"""user datasets (uploads) and saved reports with exports

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-11 12:00:00.000000

Uploaded plays live in their own tables (never in ``plays``), so private data cannot
reach public analytics, and deleting a dataset cascades to its rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_datasets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("delimiter", sa.String(length=1), nullable=False),
        sa.Column(
            "status",
            sa.Enum("uploaded", "validated", "processing", "ready", "failed", name="upload_status"),
            nullable=False,
        ),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preview", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_version", sa.String(length=64), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("stored_count", sa.Integer(), nullable=True),
        sa.Column("rejected_count", sa.Integer(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
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
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_user_datasets_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_datasets_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_datasets")),
    )
    op.create_index(
        op.f("ix_user_datasets_user_id_created_at"),
        "user_datasets",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "saved_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("team", sa.String(length=5), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=True),
        sa.Column("dataset_id", sa.UUID(), nullable=True),
        sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status", sa.Enum("pending", "ready", "failed", name="report_status"), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["user_datasets.id"],
            name=op.f("fk_saved_reports_dataset_id_user_datasets"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_saved_reports_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_saved_reports_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_reports")),
    )
    op.create_index(
        op.f("ix_saved_reports_dataset_id"), "saved_reports", ["dataset_id"], unique=False
    )
    op.create_index(
        op.f("ix_saved_reports_user_id_created_at"),
        "saved_reports",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "user_plays",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("game_key", sa.String(length=60), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=True),
        sa.Column("season_type", sa.String(length=4), nullable=True),
        sa.Column("week", sa.SmallInteger(), nullable=True),
        sa.Column("offense", sa.String(length=5), nullable=False),
        sa.Column("defense", sa.String(length=5), nullable=False),
        sa.Column("qtr", sa.SmallInteger(), nullable=True),
        sa.Column("down", sa.SmallInteger(), nullable=True),
        sa.Column("yards_to_go", sa.SmallInteger(), nullable=True),
        sa.Column("yard_line_100", sa.SmallInteger(), nullable=True),
        sa.Column("score_differential", sa.SmallInteger(), nullable=True),
        sa.Column("play_type", sa.String(length=20), nullable=False),
        sa.Column("yards_gained", sa.SmallInteger(), nullable=True),
        sa.Column("epa", sa.Float(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("complete_pass", sa.Boolean(), nullable=True),
        sa.Column("sack", sa.Boolean(), nullable=True),
        sa.Column("touchdown", sa.Boolean(), nullable=True),
        sa.Column("interception", sa.Boolean(), nullable=True),
        sa.Column("fumble_lost", sa.Boolean(), nullable=True),
        sa.Column("first_down", sa.Boolean(), nullable=True),
        sa.Column("first_down_penalty", sa.Boolean(), nullable=True),
        sa.Column("penalty", sa.Boolean(), nullable=True),
        sa.Column("third_down_converted", sa.Boolean(), nullable=True),
        sa.Column("two_point_attempt", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["user_datasets.id"],
            name=op.f("fk_user_plays_dataset_id_user_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_plays")),
    )
    op.create_index(
        op.f("ix_user_plays_dataset_id_defense"),
        "user_plays",
        ["dataset_id", "defense"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_plays_dataset_id_offense"),
        "user_plays",
        ["dataset_id", "offense"],
        unique=False,
    )
    op.create_table(
        "user_rejected_rows",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["user_datasets.id"],
            name=op.f("fk_user_rejected_rows_dataset_id_user_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_rejected_rows")),
    )
    op.create_index(
        op.f("ix_user_rejected_rows_dataset_id"), "user_rejected_rows", ["dataset_id"], unique=False
    )
    op.create_table(
        "report_exports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("report_id", sa.UUID(), nullable=False),
        sa.Column("format", sa.Enum("csv", "json", name="export_format"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("pending", "ready", "failed", name="report_status", create_type=False),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=200), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_report_exports_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["saved_reports.id"],
            name=op.f("fk_report_exports_report_id_saved_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_exports")),
    )
    op.create_index(
        op.f("ix_report_exports_report_id"), "report_exports", ["report_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_report_exports_report_id"), table_name="report_exports")
    op.drop_table("report_exports")
    op.drop_index(op.f("ix_user_rejected_rows_dataset_id"), table_name="user_rejected_rows")
    op.drop_table("user_rejected_rows")
    op.drop_index(op.f("ix_user_plays_dataset_id_offense"), table_name="user_plays")
    op.drop_index(op.f("ix_user_plays_dataset_id_defense"), table_name="user_plays")
    op.drop_table("user_plays")
    op.drop_index(op.f("ix_saved_reports_user_id_created_at"), table_name="saved_reports")
    op.drop_index(op.f("ix_saved_reports_dataset_id"), table_name="saved_reports")
    op.drop_table("saved_reports")
    op.drop_index(op.f("ix_user_datasets_user_id_created_at"), table_name="user_datasets")
    op.drop_table("user_datasets")
    for name in ("export_format", "report_status", "upload_status"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
