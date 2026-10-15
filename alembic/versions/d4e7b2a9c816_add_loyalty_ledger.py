"""add loyalty_ledger

Revision ID: d4e7b2a9c816
Revises: c83b41393b82
Create Date: 2026-10-15 10:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e7b2a9c816"
down_revision: Union[str, None] = "c83b41393b82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# LAN Sync (#716): loyalty points move by event, like credit book debts
# (#678). Each change to Customer.loyalty_points is also a loyalty_ledger
# row, which a till pushes to the Main PC. Existing points stay as they are
# (no opening rows): every machine's figure already agrees with itself, and
# only changes from now on need to travel.


def upgrade() -> None:
    op.create_table(
        "loyalty_ledger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("synced", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("loyalty_ledger", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_loyalty_ledger_customer_id"), ["customer_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_loyalty_ledger_timestamp"), ["timestamp"], unique=False)
        batch_op.create_index(batch_op.f("ix_loyalty_ledger_synced"), ["synced"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("loyalty_ledger", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_loyalty_ledger_synced"))
        batch_op.drop_index(batch_op.f("ix_loyalty_ledger_timestamp"))
        batch_op.drop_index(batch_op.f("ix_loyalty_ledger_customer_id"))
    op.drop_table("loyalty_ledger")
