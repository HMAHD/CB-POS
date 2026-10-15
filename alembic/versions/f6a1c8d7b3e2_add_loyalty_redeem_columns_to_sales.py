"""add loyalty redeem columns to sales

Revision ID: f6a1c8d7b3e2
Revises: e5f8a1c9b204
Create Date: 2026-10-15 18:35:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a1c8d7b3e2"
down_revision: Union[str, None] = "e5f8a1c9b204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.add_column(sa.Column("loyalty_points_redeemed", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("loyalty_points_value", sa.Numeric(12, 2), nullable=False, server_default="0.00"))


def downgrade() -> None:
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_column("loyalty_points_value")
        batch_op.drop_column("loyalty_points_redeemed")
