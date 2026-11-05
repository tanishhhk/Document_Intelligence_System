"""Narrated document stories, with an optional rendered video.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("strictness", sa.String(20), nullable=False),
        sa.Column("depth", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_expires_at", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("scenes", sa.Text(), nullable=True),
        sa.Column("story_source", sa.String(20), nullable=True),
        sa.Column("video_status", sa.String(20), nullable=True),
        sa.Column("video_error", sa.String(200), nullable=True),
        sa.Column("video_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name="fk_video_jobs_document_id_documents", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_video_jobs_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_jobs_document_id", "video_jobs", ["document_id"])
    op.create_index("ix_video_jobs_user_id", "video_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_video_jobs_user_id", table_name="video_jobs")
    op.drop_index("ix_video_jobs_document_id", table_name="video_jobs")
    op.drop_table("video_jobs")
