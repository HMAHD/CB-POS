"""add tax_exempt to category

Revision ID: d1af69d5c525
Revises: 659c38ff3bee
Create Date: 2026-03-09 15:06:46.671190

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1af69d5c525"
down_revision: Union[str, None] = "659c38ff3bee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("tax_exempt", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )


def downgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_column("tax_exempt")
