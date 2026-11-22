"""add product_batches and batch tracking to products, sales, purchases, stock movements, stock counts, and inventory logs (Issue #926)

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-11-22 17:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERM_CODE = "sales.override_expired_batch"
PERM_DESC = "Override expired batch block during sale"
PERM_GROUP = "Sales"

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

    # 1. Create product_batches table
    if "product_batches" not in existing_tables:
        op.create_table(
            "product_batches",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("batch_no", sa.String(length=50), nullable=True),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("mrp", sa.Numeric(precision=12, scale=2), nullable=True),
            sa.Column("cost", sa.Numeric(precision=12, scale=2), nullable=True),
            sa.Column(
                "qty_on_hand",
                sa.Numeric(precision=10, scale=3),
                nullable=False,
                server_default="0.000",
            ),
            sa.Column(
                "received_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "version_id",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "last_modified",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "batch_no IS NOT NULL OR expiry_date IS NOT NULL",
                name="ck_product_batches_has_identity",
            ),
        )
        op.create_index("ix_product_batches_product_id", "product_batches", ["product_id"])
        op.create_index("ix_product_batches_batch_no", "product_batches", ["batch_no"])
        op.create_index("ix_product_batches_expiry_date", "product_batches", ["expiry_date"])
        op.create_index("ix_product_batches_received_at", "product_batches", ["received_at"])
        op.create_index("ix_product_batches_is_active", "product_batches", ["is_active"])
        op.create_index("ix_product_batches_last_modified", "product_batches", ["last_modified"])
        op.create_index(
            "ix_product_batches_fefo",
            "product_batches",
            ["product_id", "is_active", "expiry_date", "received_at"],
        )

    # 2. Add tracks_batches to products
    if "products" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("products")}
        with op.batch_alter_table("products", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "tracks_batches" not in existing_cols:
                batch_op.add_column(sa.Column("tracks_batches", sa.Boolean(), server_default="0", nullable=False))

    # 3. Add batch_id to sale_items
    if "sale_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sale_items")}
        with op.batch_alter_table("sale_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "batch_id" not in existing_cols:
                batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_sale_items_batch_id",
                    "product_batches",
                    ["batch_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
                batch_op.create_index("ix_sale_items_batch_id", ["batch_id"])

    # 4. Add batch_id to purchase_items
    if "purchase_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("purchase_items")}
        with op.batch_alter_table("purchase_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "batch_id" not in existing_cols:
                batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_purchase_items_batch_id",
                    "product_batches",
                    ["batch_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
                batch_op.create_index("ix_purchase_items_batch_id", ["batch_id"])

    # 5. Add batch_id to stock_movements
    if "stock_movements" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("stock_movements")}
        with op.batch_alter_table("stock_movements", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "batch_id" not in existing_cols:
                batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_stock_movements_batch_id",
                    "product_batches",
                    ["batch_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
                batch_op.create_index("ix_stock_movements_batch_id", ["batch_id"])

    # 6. Add batch_id to stock_count_items
    if "stock_count_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("stock_count_items")}
        with op.batch_alter_table("stock_count_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "batch_id" not in existing_cols:
                batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_stock_count_items_batch_id",
                    "product_batches",
                    ["batch_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
                batch_op.create_index("ix_stock_count_items_batch_id", ["batch_id"])

    # 7. Add batch_id to inventory_logs
    if "inventory_logs" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("inventory_logs")}
        with op.batch_alter_table("inventory_logs", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "batch_id" not in existing_cols:
                batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_inventory_logs_batch_id",
                    "product_batches",
                    ["batch_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
                batch_op.create_index("ix_inventory_logs_batch_id", ["batch_id"])

    # 8. Seed permission sales.override_expired_batch
    if "permissions" in existing_tables:
        existing_id = conn.execute(
            sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == PERM_CODE)
        ).scalar_one_or_none()
        if existing_id is None:
            conn.execute(
                PERMISSIONS.insert(),
                [
                    {
                        "code": PERM_CODE,
                        "description": PERM_DESC,
                        "group": PERM_GROUP,
                        "last_modified": datetime.now(),
                    }
                ],
            )
            perm_id = conn.execute(
                sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == PERM_CODE)
            ).scalar_one_or_none()
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

    # 1. Remove permission grants and code
    if "permissions" in existing_tables:
        perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == PERM_CODE)).scalar_one_or_none()
        if perm_id is not None:
            if "role_permissions" in existing_tables:
                conn.execute(ROLE_PERMISSIONS.delete().where(ROLE_PERMISSIONS.c.permission_id == perm_id))
            conn.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id == perm_id))

    # 2. Drop batch_id from inventory_logs
    if "inventory_logs" in existing_tables:
        cols = {c["name"] for c in insp.get_columns("inventory_logs")}
        if "batch_id" in cols:
            with op.batch_alter_table("inventory_logs", reflect_kwargs={"resolve_fks": False}) as batch_op:
                batch_op.drop_index("ix_inventory_logs_batch_id")
                batch_op.drop_column("batch_id")

    # 3. Drop batch_id from stock_count_items
    if "stock_count_items" in existing_tables:
        cols = {c["name"] for c in insp.get_columns("stock_count_items")}
        if "batch_id" in cols:
            with op.batch_alter_table("stock_count_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
                batch_op.drop_index("ix_stock_count_items_batch_id")
                batch_op.drop_column("batch_id")

    # 4. Drop batch_id from stock_movements
    if "stock_movements" in existing_tables:
        cols = {c["name"] for c in insp.get_columns("stock_movements")}
        if "batch_id" in cols:
            with op.batch_alter_table("stock_movements", reflect_kwargs={"resolve_fks": False}) as batch_op:
                batch_op.drop_index("ix_stock_movements_batch_id")
                batch_op.drop_column("batch_id")

    # 5. Drop batch_id from purchase_items
    if "purchase_items" in existing_tables:
        cols = {c["name"] for c in insp.get_columns("purchase_items")}
        if "batch_id" in cols:
            with op.batch_alter_table("purchase_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
                batch_op.drop_index("ix_purchase_items_batch_id")
                batch_op.drop_column("batch_id")

    # 6. Drop batch_id from sale_items
    if "sale_items" in existing_tables:
        cols = {c["name"] for c in insp.get_columns("sale_items")}
        if "batch_id" in cols:
            with op.batch_alter_table("sale_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
                batch_op.drop_index("ix_sale_items_batch_id")
                batch_op.drop_column("batch_id")

    # 7. Drop tracks_batches from products
    if "products" in existing_tables:
        cols = {c["name"] for c in insp.get_columns("products")}
        if "tracks_batches" in cols:
            with op.batch_alter_table("products", reflect_kwargs={"resolve_fks": False}) as batch_op:
                batch_op.drop_column("tracks_batches")

    # 8. Drop product_batches table
    if "product_batches" in existing_tables:
        op.drop_table("product_batches")
