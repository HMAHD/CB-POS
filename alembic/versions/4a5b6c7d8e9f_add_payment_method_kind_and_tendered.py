"""add payment method kind and tendered amount (Phase 3A foundation)

Revision ID: 4a5b6c7d8e9f
Revises: 3c4d5e6f7a8b
Create Date: 2026-11-04 11:30:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a5b6c7d8e9f"
down_revision: Union[str, None] = "3c4d5e6f7a8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Add kind to payment_methods
    if "payment_methods" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("payment_methods")}
        if "kind" not in existing_cols:
            with op.batch_alter_table("payment_methods", schema=None) as batch_op:
                batch_op.add_column(sa.Column("kind", sa.String(length=20), nullable=False, server_default="OTHER"))
                batch_op.create_index("ix_payment_methods_kind", ["kind"])

    # 2. Add method_kind and tendered_amount to sale_payments
    if "sale_payments" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sale_payments")}
        with op.batch_alter_table("sale_payments", schema=None) as batch_op:
            if "method_kind" not in existing_cols:
                batch_op.add_column(
                    sa.Column("method_kind", sa.String(length=20), nullable=False, server_default="OTHER")
                )
                batch_op.create_index("ix_sale_payments_method_kind", ["method_kind"])
            if "tendered_amount" not in existing_cols:
                batch_op.add_column(sa.Column("tendered_amount", sa.Numeric(precision=12, scale=2), nullable=True))

    # 3. Backfill payment_methods.kind based on name
    if "payment_methods" in existing_tables:
        bind.execute(sa.text("UPDATE payment_methods SET kind = 'CASH' WHERE LOWER(TRIM(name)) = 'cash'"))
        bind.execute(sa.text("UPDATE payment_methods SET kind = 'CARD' WHERE LOWER(TRIM(name)) = 'card'"))
        bind.execute(sa.text("UPDATE payment_methods SET kind = 'CREDIT' WHERE LOWER(TRIM(name)) = 'credit'"))
        bind.execute(
            sa.text("UPDATE payment_methods SET kind = 'QR' WHERE LOWER(TRIM(name)) IN ('qr/mobile', 'qr', 'mobile')")
        )
        bind.execute(
            sa.text("UPDATE payment_methods SET kind = 'CHEQUE' WHERE LOWER(TRIM(name)) IN ('cheque', 'check')")
        )
        bind.execute(
            sa.text(
                "UPDATE payment_methods SET kind = 'TRANSFER' WHERE LOWER(TRIM(name)) IN ('transfer', 'bank transfer')"
            )
        )
        # Catch any method marked as cash that wasn't named 'cash'
        bind.execute(
            sa.text(
                "UPDATE payment_methods SET kind = 'CASH' WHERE (is_cash = 1 OR is_cash IS TRUE) AND kind = 'OTHER'"
            )
        )

    # 4. Backfill sale_payments.method_kind
    if "sale_payments" in existing_tables:
        # Match against payment_methods.kind by UPPER(name)
        if "payment_methods" in existing_tables:
            bind.execute(
                sa.text(
                    "UPDATE sale_payments "
                    "SET method_kind = ("
                    "  SELECT pm.kind FROM payment_methods pm "
                    "  WHERE UPPER(TRIM(pm.name)) = UPPER(TRIM(sale_payments.payment_method)) "
                    "  LIMIT 1"
                    ") "
                    "WHERE EXISTS ("
                    "  SELECT 1 FROM payment_methods pm "
                    "  WHERE UPPER(TRIM(pm.name)) = UPPER(TRIM(sale_payments.payment_method))"
                    ")"
                )
            )

        # Fix unmatched legacy rows
        bind.execute(
            sa.text(
                "UPDATE sale_payments SET method_kind = 'CASH' "
                "WHERE UPPER(TRIM(payment_method)) = 'CASH' AND (method_kind IS NULL OR method_kind = 'OTHER')"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE sale_payments SET method_kind = 'REFUND_LEGACY' WHERE UPPER(TRIM(payment_method)) = 'REFUND'"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE sale_payments SET method_kind = 'TRANSFER' "
                "WHERE UPPER(TRIM(payment_method)) IN ('TRANSFER', 'BANK TRANSFER') AND (method_kind IS NULL OR method_kind = 'OTHER')"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE sale_payments SET method_kind = 'CREDIT' "
                "WHERE UPPER(TRIM(payment_method)) = 'CREDIT' AND (method_kind IS NULL OR method_kind = 'OTHER')"
            )
        )
        bind.execute(sa.text("UPDATE sale_payments SET method_kind = 'OTHER' WHERE method_kind IS NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "sale_payments" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sale_payments")}
        with op.batch_alter_table("sale_payments", schema=None) as batch_op:
            if "method_kind" in existing_cols:
                batch_op.drop_index("ix_sale_payments_method_kind")
                batch_op.drop_column("method_kind")
            if "tendered_amount" in existing_cols:
                batch_op.drop_column("tendered_amount")

    if "payment_methods" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("payment_methods")}
        if "kind" in existing_cols:
            with op.batch_alter_table("payment_methods", schema=None) as batch_op:
                batch_op.drop_index("ix_payment_methods_kind")
                batch_op.drop_column("kind")
