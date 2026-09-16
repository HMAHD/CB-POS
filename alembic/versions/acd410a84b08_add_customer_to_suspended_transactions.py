"""add customer to suspended transactions

Revision ID: acd410a84b08
Revises: 331240ddcc04
Create Date: 2026-09-11 12:04:08.199590

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "acd410a84b08"
down_revision: Union[str, None] = "331240ddcc04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("suspended_transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("customer_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_suspended_transactions_customer_id"), ["customer_id"], unique=False)
        batch_op.create_foreign_key("fk_suspended_transactions_customer_id", "customers", ["customer_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("suspended_transactions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_suspended_transactions_customer_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_suspended_transactions_customer_id"))
        batch_op.drop_column("customer_id")
