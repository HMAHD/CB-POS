"""add daily time window to promotions

Revision ID: d2b635fce696
Revises: a8b2c4d6e9f1
Create Date: 2026-10-17 21:11:48.943039

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2b635fce696"
down_revision: Union[str, None] = "a8b2c4d6e9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("promotions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("daily_start", sa.Time(), nullable=True))
        batch_op.add_column(sa.Column("daily_end", sa.Time(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("promotions", schema=None) as batch_op:
        batch_op.drop_column("daily_end")
        batch_op.drop_column("daily_start")
