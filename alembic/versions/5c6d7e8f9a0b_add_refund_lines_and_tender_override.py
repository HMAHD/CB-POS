"""add refund lines and tender override (Phase 3A #812)

Revision ID: 5c6d7e8f9a0b
Revises: 4a5b6c7d8e9f
Create Date: 2026-11-04 18:50:00.000000

"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c6d7e8f9a0b"
down_revision: Union[str, None] = "4a5b6c7d8e9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSION = (
    "sales.refund_override_tender",
    "Sales Refund Override Tender",
    "Sales",
)
ROLE_NAMES_WITH_ACCESS = ("admin", "manager")

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
    "role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer)
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Add refund_tender_override to sales
    if "sales" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sales")}
        if "refund_tender_override" not in existing_cols:
            with op.batch_alter_table("sales", schema=None) as batch_op:
                batch_op.add_column(sa.Column("refund_tender_override", sa.String(length=20), nullable=True))

    # 2. Add refund columns and constraint to sale_items
    if "sale_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sale_items")}
        with op.batch_alter_table("sale_items", schema=None) as batch_op:
            if "refund_of_item_id" not in existing_cols:
                batch_op.add_column(sa.Column("refund_of_item_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_sale_items_refund_of_item_id", "sale_items", ["refund_of_item_id"], ["id"]
                )
                batch_op.create_index("ix_sale_items_refund_of_item_id", ["refund_of_item_id"], unique=False)
            if "refund_reason" not in existing_cols:
                batch_op.add_column(sa.Column("refund_reason", sa.String(length=200), nullable=True))
            if "refunded_qty" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "refunded_qty",
                        sa.Numeric(precision=10, scale=3),
                        nullable=False,
                        server_default="0.000",
                    )
                )
            # Add check constraint: ck_sale_items_refunded_qty
            batch_op.create_check_constraint(
                "ck_sale_items_refunded_qty",
                "refunded_qty >= 0 AND (qty < 0 OR refunded_qty <= qty)",
            )

        # 3. Data backfill: mark original lines of sales with legacy full refunds as refunded_qty = qty
        bind.execute(
            sa.text(
                """
                UPDATE sale_items
                SET refunded_qty = qty
                WHERE qty > 0 AND sale_id IN (
                    SELECT refund_of_sale_id
                    FROM sales
                    WHERE refund_of_sale_id IS NOT NULL
                )
                """
            )
        )

    # 4. Seed sales.refund_override_tender permission for Admin and Manager roles
    if "permissions" in existing_tables and "roles" in existing_tables:
        code, description, group = NEW_PERMISSION
        existing_perm = bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar()
        if existing_perm is None:
            op.bulk_insert(
                PERMISSIONS,
                [{"code": code, "description": description, "group": group, "last_modified": datetime.now()}],
            )
            perm_id = bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar()
        else:
            perm_id = existing_perm

        role_ids = list(
            bind.execute(sa.select(ROLES.c.id).where(sa.func.lower(ROLES.c.name).in_(ROLE_NAMES_WITH_ACCESS))).scalars()
        )
        granted = set(
            bind.execute(
                sa.select(ROLE_PERMISSIONS.c.role_id, ROLE_PERMISSIONS.c.permission_id).where(
                    ROLE_PERMISSIONS.c.permission_id == perm_id
                )
            ).all()
        )
        to_insert = [{"role_id": r_id, "permission_id": perm_id} for r_id in role_ids if (r_id, perm_id) not in granted]
        if to_insert:
            op.bulk_insert(ROLE_PERMISSIONS, to_insert)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "sale_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sale_items")}
        with op.batch_alter_table("sale_items", schema=None) as batch_op:
            batch_op.drop_constraint("ck_sale_items_refunded_qty", type_="check")
            if "refund_of_item_id" in existing_cols:
                batch_op.drop_index("ix_sale_items_refund_of_item_id")
                if bind.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_sale_items_refund_of_item_id", type_="foreignkey")
                batch_op.drop_column("refund_of_item_id")
            if "refund_reason" in existing_cols:
                batch_op.drop_column("refund_reason")
            if "refunded_qty" in existing_cols:
                batch_op.drop_column("refunded_qty")

    if "sales" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sales")}
        if "refund_tender_override" in existing_cols:
            with op.batch_alter_table("sales", schema=None) as batch_op:
                batch_op.drop_column("refund_tender_override")

    if "permissions" in existing_tables:
        code, _, _ = NEW_PERMISSION
        perm_id = bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar()
        if perm_id is not None:
            if "role_permissions" in existing_tables:
                bind.execute(sa.delete(ROLE_PERMISSIONS).where(ROLE_PERMISSIONS.c.permission_id == perm_id))
            bind.execute(sa.delete(PERMISSIONS).where(PERMISSIONS.c.id == perm_id))
