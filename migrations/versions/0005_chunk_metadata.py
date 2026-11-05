"""Record page ranges and the embedding model for each chunk.

Every earlier version of the application embedded chunks with
all-MiniLM-L6-v2 (384 dimensions), so existing chunks are labelled with that
model. Their page ranges stay null because pages were not tracked; retrying
processing would add them.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("document_chunks") as batch:
        batch.add_column(sa.Column("page_start", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("page_end", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("embedding_model", sa.String(100), nullable=True))
        batch.add_column(sa.Column("embedding_dim", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE document_chunks SET embedding_model = 'all-MiniLM-L6-v2', embedding_dim = 384"
    )
    with op.batch_alter_table("document_chunks") as batch:
        batch.alter_column("embedding_model", existing_type=sa.String(100), nullable=False)
        batch.alter_column("embedding_dim", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("page_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("page_count")
    with op.batch_alter_table("document_chunks") as batch:
        batch.drop_column("embedding_dim")
        batch.drop_column("embedding_model")
        batch.drop_column("page_end")
        batch.drop_column("page_start")
