"""add_supplier_payable_tables

Revision ID: 659c38ff3bee
Revises: a1192181b3ab
Create Date: 2026-02-28 16:49:02.990505

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "659c38ff3bee"
down_revision: Union[str, None] = "a1192181b3ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to suppliers table
    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.add_column(sa.Column("current_payable", sa.Numeric(12, 2), server_default="0"))
        batch_op.add_column(sa.Column("payment_terms", sa.Integer(), server_default="0"))

    # Create supplier_payments table
    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=False),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_supplier_payments_supplier_id", "supplier_payments", ["supplier_id"])
    op.create_index("ix_supplier_payments_timestamp", "supplier_payments", ["timestamp"])

    # Create supplier_ledger table
    op.create_table(
        "supplier_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("entry_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("reference_doc", sa.String(50), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_supplier_ledger_supplier_id", "supplier_ledger", ["supplier_id"])
    op.create_index("ix_supplier_ledger_timestamp", "supplier_ledger", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_supplier_ledger_timestamp", "supplier_ledger")
    op.drop_index("ix_supplier_ledger_supplier_id", "supplier_ledger")
    op.drop_table("supplier_ledger")
    op.drop_index("ix_supplier_payments_timestamp", "supplier_payments")
    op.drop_index("ix_supplier_payments_supplier_id", "supplier_payments")
    op.drop_table("supplier_payments")
    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.drop_column("payment_terms")
        batch_op.drop_column("current_payable")
