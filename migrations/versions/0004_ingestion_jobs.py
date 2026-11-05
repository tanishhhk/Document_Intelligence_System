"""Track document processing as a durable job on the documents table.

Existing documents are reconciled with the new states: documents that are
completed and have chunks stay completed. Anything else (statuses such as
"processing" or "uploaded" left by older versions, or "completed" without
any chunks) becomes "failed" with an explanation, so users can retry it.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

LEGACY_FAILURE = (
    "Processing did not finish in an earlier version of the service. "
    "Retry processing to index this document."
)


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("error_message", sa.String(500), nullable=True))
        batch.add_column(
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("lease_token", sa.String(36), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("chunk_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("processed_at", sa.DateTime(), nullable=True))

    op.execute(
        "UPDATE documents SET chunk_count = "
        "(SELECT COUNT(*) FROM document_chunks WHERE document_chunks.document_id = documents.id)"
    )
    op.execute(
        "UPDATE documents SET processed_at = upload_date "
        "WHERE status = 'completed' AND chunk_count > 0"
    )
    op.get_bind().execute(
        sa.text(
            "UPDATE documents SET status = 'failed', error_message = :message "
            "WHERE status IS NULL OR status <> 'completed' OR chunk_count = 0"
        ),
        {"message": LEGACY_FAILURE},
    )

    with op.batch_alter_table("documents") as batch:
        batch.alter_column("status", existing_type=sa.String(), nullable=False)
    op.create_index(
        "ix_documents_status_upload_date", "documents", ["status", "upload_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_documents_status_upload_date", table_name="documents")
    with op.batch_alter_table("documents") as batch:
        batch.alter_column("status", existing_type=sa.String(), nullable=True)
        batch.drop_column("processed_at")
        batch.drop_column("chunk_count")
        batch.drop_column("lease_expires_at")
        batch.drop_column("lease_token")
        batch.drop_column("attempts")
        batch.drop_column("error_message")
