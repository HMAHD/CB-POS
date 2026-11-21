"""add purchase unit conversion to products and purchase_items (Issue #937)

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-21 18:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "products" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("products")}
        with op.batch_alter_table("products", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "purchase_unit_id" not in existing_cols:
                batch_op.add_column(sa.Column("purchase_unit_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_products_purchase_unit_id",
                    "units",
                    ["purchase_unit_id"],
                    ["id"],
                )
            if "purchase_factor" not in existing_cols:
                batch_op.add_column(
                    sa.Column("purchase_factor", sa.Numeric(10, 3), server_default="1.000", nullable=False)
                )
                batch_op.create_check_constraint("ck_products_purchase_factor_positive", "purchase_factor > 0")

    if "purchase_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("purchase_items")}
        with op.batch_alter_table("purchase_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "purchase_unit_id" not in existing_cols:
                batch_op.add_column(sa.Column("purchase_unit_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_purchase_items_purchase_unit_id",
                    "units",
                    ["purchase_unit_id"],
                    ["id"],
                )
            if "purchase_factor" not in existing_cols:
                batch_op.add_column(
                    sa.Column("purchase_factor", sa.Numeric(10, 3), server_default="1.000", nullable=False)
                )
            if "purchase_qty" not in existing_cols:
                batch_op.add_column(sa.Column("purchase_qty", sa.Numeric(10, 3), nullable=True))
            if "purchase_unit_cost" not in existing_cols:
                batch_op.add_column(sa.Column("purchase_unit_cost", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "purchase_items" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("purchase_items")}
        with op.batch_alter_table("purchase_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "purchase_unit_cost" in existing_cols:
                batch_op.drop_column("purchase_unit_cost")
            if "purchase_qty" in existing_cols:
                batch_op.drop_column("purchase_qty")
            if "purchase_factor" in existing_cols:
                batch_op.drop_column("purchase_factor")
            if "purchase_unit_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    for fk in insp.get_foreign_keys("purchase_items"):
                        if "purchase_unit_id" in fk.get("constrained_columns", []):
                            fk_name = fk.get("name")
                            if fk_name:
                                batch_op.drop_constraint(fk_name, type_="foreignkey")
                batch_op.drop_column("purchase_unit_id")

    if "products" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("products")}
        with op.batch_alter_table("products", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "purchase_factor" in existing_cols:
                batch_op.drop_constraint("ck_products_purchase_factor_positive", type_="check")
                batch_op.drop_column("purchase_factor")
            if "purchase_unit_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    for fk in insp.get_foreign_keys("products"):
                        if "purchase_unit_id" in fk.get("constrained_columns", []):
                            fk_name = fk.get("name")
                            if fk_name:
                                batch_op.drop_constraint(fk_name, type_="foreignkey")
                batch_op.drop_column("purchase_unit_id")
