"""add sync_id_map

Revision ID: e177823b8aa9
Revises: b4d6fbce9cf4
Create Date: 2026-10-07 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e177823b8aa9"
down_revision: Union[str, None] = "b4d6fbce9cf4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Main PC: (till, id space, till's own row id) -> the row id the Main PC
# assigned (#671). Starts empty: rows synced before this existed keep the
# till's id they were stored under, and the sync server adopts them into
# this table the first time a till refers to them again.


def upgrade() -> None:
    op.create_table(
        "sync_id_map",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("origin_terminal_id", sa.String(length=50), nullable=False),
        sa.Column("table_name", sa.String(length=50), nullable=False),
        sa.Column("local_id", sa.Integer(), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("origin_terminal_id", "table_name", "local_id", name="uq_sync_id_map_origin_local"),
    )
    with op.batch_alter_table("sync_id_map", schema=None) as batch_op:
        batch_op.create_index("ix_sync_id_map_table_server", ["table_name", "server_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sync_id_map", schema=None) as batch_op:
        batch_op.drop_index("ix_sync_id_map_table_server")
    op.drop_table("sync_id_map")
