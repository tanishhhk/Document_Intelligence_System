"""Add cascading foreign keys, chunk uniqueness and lookup indexes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Lets batch mode on SQLite address foreign keys that were created unnamed.
NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}

FOREIGN_KEYS = [
    ("documents", "user_id", "users"),
    ("document_chunks", "document_id", "documents"),
    ("upload_idempotency", "user_id", "users"),
]


def _replace_foreign_key(table, column, referred, ondelete):
    existing = [
        fk
        for fk in sa.inspect(op.get_bind()).get_foreign_keys(table)
        if fk["constrained_columns"] == [column]
    ]
    name = f"fk_{table}_{column}_{referred}"
    with op.batch_alter_table(table, naming_convention=NAMING) as batch:
        for fk in existing:
            batch.drop_constraint(fk["name"] or name, type_="foreignkey")
        batch.create_foreign_key(name, referred, [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM (SELECT document_id, chunk_index FROM document_chunks "
            "GROUP BY document_id, chunk_index HAVING COUNT(*) > 1) AS duplicated"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError(
            f"{duplicates} documents have repeated chunk indexes. Remove the duplicate "
            "rows from document_chunks before running this migration."
        )

    for table, column, referred in FOREIGN_KEYS:
        _replace_foreign_key(table, column, referred, "CASCADE")

    with op.batch_alter_table("document_chunks") as batch:
        batch.create_unique_constraint(
            "uq_document_chunks_document_index", ["document_id", "chunk_index"]
        )
    op.create_index(
        "ix_documents_user_id_upload_date", "documents", ["user_id", "upload_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_documents_user_id_upload_date", table_name="documents")
    with op.batch_alter_table("document_chunks") as batch:
        batch.drop_constraint("uq_document_chunks_document_index", type_="unique")
    for table, column, referred in FOREIGN_KEYS:
        _replace_foreign_key(table, column, referred, None)
