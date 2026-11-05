"""Profession and focus on users, and daily usage counters.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("profession", sa.String(20), nullable=True))
        batch.add_column(sa.Column("focus", sa.String(20), nullable=True))
    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_usage_counters_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day", "kind", name="uq_usage_counters_user_day_kind"),
    )


def downgrade() -> None:
    op.drop_table("usage_counters")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("focus")
        batch.drop_column("profession")
