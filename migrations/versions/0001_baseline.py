"""Baseline schema previously created by Base.metadata.create_all.

Tables are created only when missing, so databases created by earlier
versions of the application (with some or all of these tables) can be
upgraded in place. Existing tables and rows are left untouched.

Revision ID: 0001
Revises:
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _missing(table: str) -> bool:
    return not sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if _missing("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if _missing("documents"):
        op.create_table(
            "documents",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("upload_date", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
        )

    if _missing("document_chunks"):
        op.create_table(
            "document_chunks",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False
            ),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("chunk_text", sa.Text(), nullable=False),
            sa.Column("embedding", sa.Text(), nullable=False),
        )

    if _missing("revoked_tokens"):
        op.create_table(
            "revoked_tokens",
            sa.Column("jti", sa.String(), primary_key=True),
            sa.Column("expires_at", sa.Integer(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])

    if _missing("upload_idempotency"):
        op.create_table(
            "upload_idempotency",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=False),
            sa.Column("document_id", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("expires_at", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "idempotency_key", name="uq_upload_key_per_user"),
        )
        op.create_index("ix_upload_idempotency_user_id", "upload_idempotency", ["user_id"])
        op.create_index(
            "ix_upload_idempotency_expires_at", "upload_idempotency", ["expires_at"]
        )


def downgrade() -> None:
    # Downgrading past the baseline removes every application table.
    for table in (
        "upload_idempotency",
        "revoked_tokens",
        "document_chunks",
        "documents",
        "users",
    ):
        op.drop_table(table)
