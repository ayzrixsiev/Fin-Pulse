"""add user_stats table

Revision ID: b8a3c2b1d6f4
Revises: 210164c2f875
Create Date: 2026-02-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8a3c2b1d6f4"
down_revision: Union[str, Sequence[str], None] = "210164c2f875"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_stats",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("total_transactions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_income", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("total_expense", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column(
            "avg_transaction_amount", sa.Numeric(15, 2), server_default="0", nullable=False
        ),
        sa.Column("spent_by_category", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users_table.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("user_stats")
