"""add tax_invoices, tax_invoice_lines, tax_invoice_sequences, tax_credit_notes, and sales.tax_invoice permission (Issue #814)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-12 10:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODE = "sales.tax_invoice"
DESCRIPTION = "Issue and print official VAT Tax Invoices"
GROUP = "Sales"

PERMISSIONS = sa.table(
    "permissions",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("description", sa.String),
    sa.column("group", sa.String),
    sa.column("last_modified", sa.DateTime),
)
ROLES = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String))
ROLE_PERMISSIONS = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("permission_id", sa.Integer),
)


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    # 1. Create tax_invoices
    if "tax_invoices" not in existing_tables:
        op.create_table(
            "tax_invoices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id"), nullable=False, unique=True),
            sa.Column("serial", sa.String(length=40), nullable=False, unique=True),
            sa.Column("issued_at", sa.DateTime(), nullable=False),
            sa.Column("supply_date", sa.Date(), nullable=False),
            sa.Column("payment_method", sa.String(length=50), nullable=False),
            sa.Column("issued_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("supplier_name", sa.String(length=255), nullable=False),
            sa.Column("supplier_address", sa.Text(), nullable=False),
            sa.Column("supplier_phone", sa.String(length=50), nullable=False),
            sa.Column("supplier_tin", sa.String(length=20), nullable=False),
            sa.Column("buyer_name", sa.String(length=255), nullable=False),
            sa.Column("buyer_address", sa.Text(), nullable=False),
            sa.Column("buyer_phone", sa.String(length=50), nullable=True),
            sa.Column("buyer_tin", sa.String(length=20), nullable=False),
            sa.Column("issue_language", sa.String(length=5), server_default="en", nullable=False),
            sa.Column("print_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("original_printed_at", sa.DateTime(), nullable=True),
            sa.Column("subtotal_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), server_default="0.00", nullable=False),
            sa.Column("net_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("tax_vat", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("amount_in_words", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_tax_invoices_serial", "tax_invoices", ["serial"], unique=True)
        op.create_index("ix_tax_invoices_sale_id", "tax_invoices", ["sale_id"], unique=True)

    # 2. Create tax_invoice_lines
    if "tax_invoice_lines" not in existing_tables:
        op.create_table(
            "tax_invoice_lines",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "tax_invoice_id",
                sa.Integer(),
                sa.ForeignKey("tax_invoices.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("item_number", sa.Integer(), nullable=False),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("item_code_snapshot", sa.String(length=50), nullable=True),
            sa.Column("product_name_snapshot", sa.String(length=255), nullable=False),
            sa.Column("unit_snapshot", sa.String(length=20), server_default="pcs", nullable=False),
            sa.Column("quantity", sa.Numeric(precision=10, scale=3), nullable=False),
            sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), server_default="0.00", nullable=False),
            sa.Column("net_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column("vat_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        )
        op.create_index("ix_tax_invoice_lines_tax_invoice_id", "tax_invoice_lines", ["tax_invoice_id"])

    # 3. Create tax_invoice_sequences
    if "tax_invoice_sequences" not in existing_tables:
        op.create_table(
            "tax_invoice_sequences",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("prefix", sa.String(length=30), nullable=False, unique=True),
            sa.Column("last_seq", sa.Integer(), server_default="0", nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_tax_invoice_sequences_prefix", "tax_invoice_sequences", ["prefix"], unique=True)

    # 4. Create tax_credit_notes
    if "tax_credit_notes" not in existing_tables:
        op.create_table(
            "tax_credit_notes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tax_invoice_id", sa.Integer(), sa.ForeignKey("tax_invoices.id"), nullable=False),
            sa.Column("refund_sale_id", sa.Integer(), sa.ForeignKey("sales.id"), nullable=False, unique=True),
            sa.Column("serial", sa.String(length=40), nullable=False, unique=True),
            sa.Column("issued_at", sa.DateTime(), nullable=False),
            sa.Column("issued_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("net_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("tax_vat", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("amount_in_words", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_tax_credit_notes_serial", "tax_credit_notes", ["serial"], unique=True)
        op.create_index("ix_tax_credit_notes_tax_invoice_id", "tax_credit_notes", ["tax_invoice_id"])

    # 5. Seed permission sales.tax_invoice
    if "permissions" in existing_tables:
        existing_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == CODE)).scalar_one_or_none()
        if existing_id is None:
            conn.execute(
                PERMISSIONS.insert(),
                [{"code": CODE, "description": DESCRIPTION, "group": GROUP, "last_modified": datetime.now()}],
            )
            perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == CODE)).scalar_one_or_none()
        else:
            perm_id = existing_id

        if perm_id is not None and "roles" in existing_tables and "role_permissions" in existing_tables:
            role_ids = conn.execute(sa.select(ROLES.c.id).where(ROLES.c.name.in_(["Admin", "Manager"]))).scalars().all()
            for r_id in role_ids:
                has_grant = conn.execute(
                    sa.select(ROLE_PERMISSIONS.c.permission_id).where(
                        ROLE_PERMISSIONS.c.role_id == r_id,
                        ROLE_PERMISSIONS.c.permission_id == perm_id,
                    )
                ).scalar_one_or_none()
                if not has_grant:
                    conn.execute(
                        ROLE_PERMISSIONS.insert(),
                        [{"role_id": r_id, "permission_id": perm_id}],
                    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    # 1. Revoke permission
    if "permissions" in existing_tables:
        perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == CODE)).scalar_one_or_none()
        if perm_id is not None and "role_permissions" in existing_tables:
            conn.execute(sa.delete(ROLE_PERMISSIONS).where(ROLE_PERMISSIONS.c.permission_id == perm_id))
            conn.execute(sa.delete(PERMISSIONS).where(PERMISSIONS.c.id == perm_id))

    # 2. Drop tables in reverse order
    if "tax_credit_notes" in existing_tables:
        op.drop_table("tax_credit_notes")
    if "tax_invoice_sequences" in existing_tables:
        op.drop_table("tax_invoice_sequences")
    if "tax_invoice_lines" in existing_tables:
        op.drop_table("tax_invoice_lines")
    if "tax_invoices" in existing_tables:
        op.drop_table("tax_invoices")
