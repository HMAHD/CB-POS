"""add synced to inventory_logs (#903)

Revision ID: 2b3c4d5e6f7a
Revises: 1f2e3d4c5b6a
Create Date: 2026-11-03 01:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b3c4d5e6f7a"
down_revision: Union[str, None] = "1f2e3d4c5b6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("inventory_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("synced", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index("ix_inventory_logs_synced", ["synced"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("inventory_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_inventory_logs_synced")
        batch_op.drop_column("synced")
