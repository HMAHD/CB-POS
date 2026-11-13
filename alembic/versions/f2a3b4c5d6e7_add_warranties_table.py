"""add warranties table for per-unit warranty tracking (Issue #822, #820)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-12 21:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "warranties" not in existing_tables:
        op.create_table(
            "warranties",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(length=60), nullable=False),
            sa.Column("unit_index", sa.Integer(), server_default="1", nullable=False),
            sa.Column("sale_id", sa.Integer(), nullable=False),
            sa.Column("sale_item_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("policy_id", sa.Integer(), nullable=True),
            sa.Column("customer_name_snapshot", sa.String(length=100), nullable=True),
            sa.Column("customer_phone_snapshot", sa.String(length=20), nullable=True),
            sa.Column("serial_number", sa.String(length=64), nullable=True),
            sa.Column("warranty_type", sa.String(length=20), nullable=False),
            sa.Column("duration", sa.Integer(), nullable=False),
            sa.Column("duration_unit", sa.String(length=10), nullable=False),
            sa.Column("remedy", sa.String(length=30), nullable=False),
            sa.Column("provider_name", sa.String(length=100), nullable=True),
            sa.Column("terms_text", sa.Text(), nullable=True),
            sa.Column("exclusions_text", sa.Text(), nullable=True),
            sa.Column("lang", sa.String(length=5), server_default="en", nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
            sa.Column("cancelled_by_sale_id", sa.Integer(), nullable=True),
            sa.Column("covers_warranty_id", sa.Integer(), nullable=True),
            sa.Column("replaces_warranty_id", sa.Integer(), nullable=True),
            sa.Column("terminal_id", sa.String(length=50), nullable=True),
            sa.Column("synced", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("last_modified", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["sale_item_id"], ["sale_items.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["policy_id"], ["warranty_policies.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["cancelled_by_sale_id"], ["sales.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["covers_warranty_id"], ["warranties.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["replaces_warranty_id"], ["warranties.id"], ondelete="RESTRICT"),
            sa.CheckConstraint("duration > 0", name="ck_warranties_duration"),
            sa.CheckConstraint("duration_unit IN ('DAYS', 'MONTHS', 'YEARS')", name="ck_warranties_duration_unit"),
            sa.CheckConstraint(
                "warranty_type IN ('SHOP', 'MANUFACTURER', 'EXTENDED')", name="ck_warranties_warranty_type"
            ),
            sa.CheckConstraint(
                "remedy IN ('REPAIR_OR_REPLACE', 'REPAIR_ONLY', 'REPLACE_ONLY', 'REFUND')",
                name="ck_warranties_remedy",
            ),
            sa.CheckConstraint(
                "status IN ('ACTIVE', 'VOID', 'CANCELLED', 'REPLACED', 'CLOSED')",
                name="ck_warranties_status",
            ),
            sa.CheckConstraint("end_date >= start_date", name="ck_warranties_dates"),
            sa.CheckConstraint("unit_index > 0", name="ck_warranties_unit_index"),
        )
        op.create_index("ix_warranties_code", "warranties", ["code"], unique=True)
        op.create_index("ix_warranties_sale_id", "warranties", ["sale_id"])
        op.create_index("ix_warranties_sale_item_id", "warranties", ["sale_item_id"])
        op.create_index("ix_warranties_product_id", "warranties", ["product_id"])
        op.create_index("ix_warranties_customer_id", "warranties", ["customer_id"])
        op.create_index("ix_warranties_policy_id", "warranties", ["policy_id"])
        op.create_index("ix_warranties_serial_number", "warranties", ["serial_number"])
        op.create_index("ix_warranties_status", "warranties", ["status"])
        op.create_index("ix_warranties_start_date", "warranties", ["start_date"])
        op.create_index("ix_warranties_end_date", "warranties", ["end_date"])
        op.create_index("ix_warranties_cancelled_by_sale_id", "warranties", ["cancelled_by_sale_id"])
        op.create_index("ix_warranties_covers_warranty_id", "warranties", ["covers_warranty_id"])
        op.create_index("ix_warranties_replaces_warranty_id", "warranties", ["replaces_warranty_id"])
        op.create_index("ix_warranties_terminal_id", "warranties", ["terminal_id"])
        op.create_index("ix_warranties_synced", "warranties", ["synced"])
        op.create_index("ix_warranties_last_modified", "warranties", ["last_modified"])
        op.create_index(
            "ix_warranties_sale_item_status_unit",
            "warranties",
            ["sale_item_id", "status", "unit_index"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "warranties" in existing_tables:
        op.drop_table("warranties")
