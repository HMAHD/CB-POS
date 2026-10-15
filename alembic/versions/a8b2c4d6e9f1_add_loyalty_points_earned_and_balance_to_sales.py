"""add loyalty points earned and balance to sales

Revision ID: a8b2c4d6e9f1
Revises: f6a1c8d7b3e2
Create Date: 2026-10-15 19:15:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b2c4d6e9f1"
down_revision: Union[str, None] = "f6a1c8d7b3e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.add_column(sa.Column("loyalty_points_earned", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("loyalty_points_balance", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_column("loyalty_points_balance")
        batch_op.drop_column("loyalty_points_earned")
