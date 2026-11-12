"""add warranty_policies table, category and product warranty fields, and warranty permissions (Issue #821)

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-11-12 18:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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

WARRANTY_PERMISSIONS = [
    {
        "code": "warranty.view",
        "description": "View warranty policies and product coverage",
        "group": "Warranty",
        "roles": ["Admin", "Manager", "Cashier"],
    },
    {
        "code": "warranty.edit",
        "description": "Assign warranty policies to products and categories",
        "group": "Warranty",
        "roles": ["Admin", "Manager"],
    },
    {
        "code": "warranty.manage_policies",
        "description": "Create, edit and deactivate warranty policies",
        "group": "Warranty",
        "roles": ["Admin", "Manager"],
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    # 1. Create warranty_policies table
    if "warranty_policies" not in existing_tables:
        op.create_table(
            "warranty_policies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("name_si", sa.String(length=100), nullable=True),
            sa.Column("name_ta", sa.String(length=100), nullable=True),
            sa.Column("warranty_type", sa.String(length=20), nullable=False),
            sa.Column("duration", sa.Integer(), nullable=False),
            sa.Column("duration_unit", sa.String(length=10), nullable=False),
            sa.Column("remedy", sa.String(length=30), nullable=False),
            sa.Column("provider_name", sa.String(length=100), nullable=True),
            sa.Column("terms_text", sa.Text(), nullable=True),
            sa.Column("terms_text_si", sa.Text(), nullable=True),
            sa.Column("terms_text_ta", sa.Text(), nullable=True),
            sa.Column("exclusions_text", sa.Text(), nullable=True),
            sa.Column("exclusions_text_si", sa.Text(), nullable=True),
            sa.Column("exclusions_text_ta", sa.Text(), nullable=True),
            sa.Column("supplier_cover_months", sa.Integer(), server_default="0", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("is_template", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("synced", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, default=datetime.now),
            sa.Column("last_modified", sa.DateTime(), nullable=False, default=datetime.now),
            sa.CheckConstraint("duration > 0", name="ck_warranty_policy_duration"),
            sa.CheckConstraint("duration_unit IN ('DAYS', 'MONTHS', 'YEARS')", name="ck_warranty_policy_unit"),
            sa.CheckConstraint("warranty_type IN ('SHOP', 'MANUFACTURER', 'EXTENDED')", name="ck_warranty_policy_type"),
            sa.CheckConstraint(
                "remedy IN ('REPAIR_OR_REPLACE', 'REPAIR_ONLY', 'REPLACE_ONLY', 'REFUND')",
                name="ck_warranty_policy_remedy",
            ),
        )
        op.create_index("ix_warranty_policies_is_active", "warranty_policies", ["is_active"])
        op.create_index("ix_warranty_policies_last_modified", "warranty_policies", ["last_modified"])

    # 2. Add default_warranty_policy_id to categories table
    if "categories" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("categories")}
        with op.batch_alter_table("categories", schema=None) as batch_op:
            if "default_warranty_policy_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "default_warranty_policy_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )
                batch_op.create_foreign_key(
                    "fk_categories_default_warranty_policy_id",
                    "warranty_policies",
                    ["default_warranty_policy_id"],
                    ["id"],
                )
                batch_op.create_index(
                    "ix_categories_default_warranty_policy_id",
                    ["default_warranty_policy_id"],
                )

    # 3. Add warranty fields and serial_mode to products table
    if "products" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("products")}
        with op.batch_alter_table("products", schema=None) as batch_op:
            if "warranty_policy_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "warranty_policy_id",
                        sa.Integer(),
                        nullable=True,
                    )
                )
                batch_op.create_foreign_key(
                    "fk_products_warranty_policy_id",
                    "warranty_policies",
                    ["warranty_policy_id"],
                    ["id"],
                )
                batch_op.create_index(
                    "ix_products_warranty_policy_id",
                    ["warranty_policy_id"],
                )
            if "warranty_override" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "warranty_override",
                        sa.String(length=10),
                        server_default="INHERIT",
                        nullable=False,
                    )
                )
            if "serial_mode" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "serial_mode",
                        sa.String(length=10),
                        server_default="OFF",
                        nullable=False,
                    )
                )

    # 4. Insert permissions and map to roles
    if "permissions" in existing_tables:
        now = datetime.now()
        for pdef in WARRANTY_PERMISSIONS:
            code = pdef["code"]
            existing_id = conn.execute(
                sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)
            ).scalar_one_or_none()

            if existing_id is None:
                conn.execute(
                    PERMISSIONS.insert(),
                    [
                        {
                            "code": code,
                            "description": pdef["description"],
                            "group": pdef["group"],
                            "last_modified": now,
                        }
                    ],
                )
                perm_id = conn.execute(
                    sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)
                ).scalar_one_or_none()
            else:
                perm_id = existing_id

            if perm_id is not None and "roles" in existing_tables and "role_permissions" in existing_tables:
                role_ids = conn.execute(sa.select(ROLES.c.id).where(ROLES.c.name.in_(pdef["roles"]))).scalars().all()
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

    # 1. Revoke and delete permissions
    if "permissions" in existing_tables:
        for pdef in WARRANTY_PERMISSIONS:
            code = pdef["code"]
            perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar_one_or_none()
            if perm_id is not None:
                if "role_permissions" in existing_tables:
                    conn.execute(sa.delete(ROLE_PERMISSIONS).where(ROLE_PERMISSIONS.c.permission_id == perm_id))
                conn.execute(sa.delete(PERMISSIONS).where(PERMISSIONS.c.id == perm_id))

    # 2. Batch alter products to drop columns
    if "products" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("products")}
        with op.batch_alter_table("products", schema=None) as batch_op:
            if "warranty_policy_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_products_warranty_policy_id", type_="foreignkey")
                batch_op.drop_index("ix_products_warranty_policy_id")
                batch_op.drop_column("warranty_policy_id")
            if "warranty_override" in existing_cols:
                batch_op.drop_column("warranty_override")
            if "serial_mode" in existing_cols:
                batch_op.drop_column("serial_mode")

    # 3. Batch alter categories to drop columns
    if "categories" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("categories")}
        with op.batch_alter_table("categories", schema=None) as batch_op:
            if "default_warranty_policy_id" in existing_cols:
                if conn.dialect.name != "sqlite":
                    batch_op.drop_constraint("fk_categories_default_warranty_policy_id", type_="foreignkey")
                batch_op.drop_index("ix_categories_default_warranty_policy_id")
                batch_op.drop_column("default_warranty_policy_id")

    # 4. Drop warranty_policies table
    if "warranty_policies" in existing_tables:
        op.drop_table("warranty_policies")
