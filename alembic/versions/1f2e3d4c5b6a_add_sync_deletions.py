"""add sync_deletions table (#871)

Revision ID: 1f2e3d4c5b6a
Revises: 7a8f1b2c3d4e
Create Date: 2026-11-02 23:45:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f2e3d4c5b6a"
down_revision: Union[str, None] = "7a8f1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_deletions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("table_name", sa.String(length=50), nullable=False),
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("natural_key", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_deletions_table_row", "sync_deletions", ["table_name", "row_id"], unique=False)
    op.create_index("ix_sync_deletions_deleted_at", "sync_deletions", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sync_deletions_deleted_at", table_name="sync_deletions")
    op.drop_index("ix_sync_deletions_table_row", table_name="sync_deletions")
    op.drop_table("sync_deletions")
