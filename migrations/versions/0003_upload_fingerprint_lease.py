"""Store the uploaded file's SHA-256 and a processing lease per upload key.

The lease token identifies which request currently owns a key, so a request
that outlived its lease cannot mark the key completed.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The columns stay nullable: keys recorded before this revision have no
    # fingerprint, and a missing lease is treated as already expired.
    with op.batch_alter_table("upload_idempotency") as batch:
        batch.add_column(sa.Column("payload_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("lease_token", sa.String(36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("upload_idempotency") as batch:
        batch.drop_column("lease_token")
        batch.drop_column("lease_expires_at")
        batch.drop_column("payload_sha256")
