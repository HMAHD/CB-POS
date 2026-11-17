"""add extended warranty and claim reporting fields (Issues #829, #830, #820)

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-17 19:30:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    # 1. warranty_policies: extended_starts
    if "warranty_policies" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("warranty_policies")}
        with op.batch_alter_table("warranty_policies", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "extended_starts" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "extended_starts",
                        sa.String(length=20),
                        server_default="AFTER_BASE",
                        nullable=False,
                    )
                )

    # 2. products: is_warranty_plan, plan_policy_id, plan_category_id
    if "products" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("products")}
        with op.batch_alter_table("products", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "is_warranty_plan" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "is_warranty_plan",
                        sa.Boolean(),
                        server_default="0",
                        nullable=False,
                    )
                )
            if "plan_policy_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "plan_policy_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )
                batch_op.create_foreign_key(
                    "fk_products_plan_policy_id",
                    "warranty_policies",
                    ["plan_policy_id"],
                    ["id"],
                )
                batch_op.create_index(
                    "ix_products_plan_policy_id",
                    ["plan_policy_id"],
                )
            if "plan_category_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "plan_category_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )
                batch_op.create_foreign_key(
                    "fk_products_plan_category_id",
                    "categories",
                    ["plan_category_id"],
                    ["id"],
                )
                batch_op.create_index(
                    "ix_products_plan_category_id",
                    ["plan_category_id"],
                )

    # 3. sale_items: covered_item_id
    if "sale_items" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("sale_items")}
        with op.batch_alter_table("sale_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "covered_item_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "covered_item_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )
                batch_op.create_foreign_key(
                    "fk_sale_items_covered_item_id",
                    "sale_items",
                    ["covered_item_id"],
                    ["id"],
                )
                batch_op.create_index(
                    "ix_sale_items_covered_item_id",
                    ["covered_item_id"],
                )

    # 4. warranties: plan_sale_item_id
    if "warranties" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("warranties")}
        with op.batch_alter_table("warranties", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "plan_sale_item_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "plan_sale_item_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )
                batch_op.create_foreign_key(
                    "fk_warranties_plan_sale_item_id",
                    "sale_items",
                    ["plan_sale_item_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
                batch_op.create_index(
                    "ix_warranties_plan_sale_item_id",
                    ["plan_sale_item_id"],
                )

    # 5. warranty_claims: expected_ready_date, replacement_cost_snapshot
    if "warranty_claims" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("warranty_claims")}
        with op.batch_alter_table("warranty_claims", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "expected_ready_date" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "expected_ready_date",
                        sa.Date(),
                        nullable=True,
                    )
                )
                batch_op.create_index(
                    "ix_warranty_claims_expected_ready_date",
                    ["expected_ready_date"],
                )
            if "replacement_cost_snapshot" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "replacement_cost_snapshot",
                        sa.Numeric(12, 2),
                        nullable=True,
                    )
                )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    # 5. warranty_claims
    if "warranty_claims" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("warranty_claims")}
        existing_indexes = {c["name"] for c in insp.get_indexes("warranty_claims")}
        with op.batch_alter_table("warranty_claims", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "replacement_cost_snapshot" in existing_cols:
                batch_op.drop_column("replacement_cost_snapshot")
            if "ix_warranty_claims_expected_ready_date" in existing_indexes:
                batch_op.drop_index("ix_warranty_claims_expected_ready_date")
            if "expected_ready_date" in existing_cols:
                batch_op.drop_column("expected_ready_date")

    # 4. warranties
    if "warranties" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("warranties")}
        existing_indexes = {c["name"] for c in insp.get_indexes("warranties")}
        with op.batch_alter_table("warranties", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "ix_warranties_plan_sale_item_id" in existing_indexes:
                batch_op.drop_index("ix_warranties_plan_sale_item_id")
            if "plan_sale_item_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_warranties_plan_sale_item_id", type_="foreignkey")
                batch_op.drop_column("plan_sale_item_id")

    # 3. sale_items
    if "sale_items" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("sale_items")}
        existing_indexes = {c["name"] for c in insp.get_indexes("sale_items")}
        with op.batch_alter_table("sale_items", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "ix_sale_items_covered_item_id" in existing_indexes:
                batch_op.drop_index("ix_sale_items_covered_item_id")
            if "covered_item_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_sale_items_covered_item_id", type_="foreignkey")
                batch_op.drop_column("covered_item_id")

    # 2. products
    if "products" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("products")}
        existing_indexes = {c["name"] for c in insp.get_indexes("products")}
        with op.batch_alter_table("products", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "ix_products_plan_category_id" in existing_indexes:
                batch_op.drop_index("ix_products_plan_category_id")
            if "plan_category_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_products_plan_category_id", type_="foreignkey")
                batch_op.drop_column("plan_category_id")

            if "ix_products_plan_policy_id" in existing_indexes:
                batch_op.drop_index("ix_products_plan_policy_id")
            if "plan_policy_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_products_plan_policy_id", type_="foreignkey")
                batch_op.drop_column("plan_policy_id")

            if "is_warranty_plan" in existing_cols:
                batch_op.drop_column("is_warranty_plan")

    # 1. warranty_policies
    if "warranty_policies" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("warranty_policies")}
        with op.batch_alter_table("warranty_policies", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "extended_starts" in existing_cols:
                batch_op.drop_column("extended_starts")
