"""add warranty_claims, warranty_claim_events, and warranty claim permissions (Issue #826, #820)

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-11-17 12:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
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

CLAIM_PERMISSIONS = [
    {
        "code": "warranty.claim_create",
        "description": "Create and intake warranty claims",
        "group": "Warranty",
        "roles": ["Admin", "Manager", "Cashier"],
    },
    {
        "code": "warranty.claim_resolve",
        "description": "Resolve, reject, or void warranty claims",
        "group": "Warranty",
        "roles": ["Admin", "Manager"],
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    # 1. Create warranty_claims table (JTI child of documents.id)
    if "warranty_claims" not in existing_tables:
        op.create_table(
            "warranty_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("warranty_id", sa.Integer(), nullable=True),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("customer_name_snapshot", sa.String(length=100), nullable=True),
            sa.Column("customer_phone_snapshot", sa.String(length=20), nullable=True),
            sa.Column("item_serial", sa.String(length=64), nullable=True),
            sa.Column("claim_status", sa.String(length=30), server_default="INTAKE", nullable=False),
            sa.Column("intake_date", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("defect_description", sa.Text(), nullable=False),
            sa.Column("item_condition", sa.Text(), nullable=True),
            sa.Column("accessories_received", sa.Text(), nullable=True),
            sa.Column("is_covered", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("resolution", sa.String(length=30), nullable=True),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("replacement_warranty_id", sa.Integer(), nullable=True),
            sa.Column("replacement_serial", sa.String(length=64), nullable=True),
            sa.Column("repair_cost", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
            sa.Column("charge_customer", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
            sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("collected_by_name", sa.String(length=100), nullable=True),
            sa.Column("collected_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["id"], ["documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["warranty_id"], ["warranties.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["replacement_warranty_id"], ["warranties.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.CheckConstraint(
                "claim_status IN ('INTAKE', 'IN_INSPECTION', 'SUPPLIER_DISPATCHED', 'SUPPLIER_RETURNED', 'RESOLVED', 'COLLECTED', 'REJECTED', 'VOID', 'CANCELLED')",
                name="ck_warranty_claims_status",
            ),
            sa.CheckConstraint(
                "resolution IS NULL OR resolution IN ('REPAIRED', 'REPLACED_SAME', 'REPLACED_DIFFERENT', 'REFUNDED', 'REJECTED_UNCOVERED')",
                name="ck_warranty_claims_resolution",
            ),
        )
        op.create_index("ix_warranty_claims_warranty_id", "warranty_claims", ["warranty_id"])
        op.create_index("ix_warranty_claims_product_id", "warranty_claims", ["product_id"])
        op.create_index("ix_warranty_claims_customer_id", "warranty_claims", ["customer_id"])
        op.create_index("ix_warranty_claims_claim_status", "warranty_claims", ["claim_status"])
        op.create_index("ix_warranty_claims_item_serial", "warranty_claims", ["item_serial"])
        op.create_index("ix_warranty_claims_intake_date", "warranty_claims", ["intake_date"])
        op.create_index("ix_warranty_claims_replacement_warranty_id", "warranty_claims", ["replacement_warranty_id"])
        op.create_index("ix_warranty_claims_resolved_by_user_id", "warranty_claims", ["resolved_by_user_id"])

        # Partial unique index (1 open claim per warranty) supported on SQLite and PostgreSQL
        op.execute(
            """
            CREATE UNIQUE INDEX uq_warranty_active_claim
            ON warranty_claims (warranty_id)
            WHERE claim_status NOT IN ('COLLECTED', 'REJECTED', 'VOID', 'CANCELLED')
              AND warranty_id IS NOT NULL;
            """
        )

    # 2. Create warranty_claim_events table
    if "warranty_claim_events" not in existing_tables:
        op.create_table(
            "warranty_claim_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("claim_id", sa.Integer(), nullable=False),
            sa.Column("from_status", sa.String(length=30), nullable=True),
            sa.Column("to_status", sa.String(length=30), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("event_time", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("synced", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.ForeignKeyConstraint(["claim_id"], ["warranty_claims.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        )
        op.create_index("ix_warranty_claim_events_claim_id", "warranty_claim_events", ["claim_id"])
        op.create_index("ix_warranty_claim_events_user_id", "warranty_claim_events", ["user_id"])
        op.create_index("ix_warranty_claim_events_event_time", "warranty_claim_events", ["event_time"])
        op.create_index("ix_warranty_claim_events_synced", "warranty_claim_events", ["synced"])

    # 3. Seed Permissions
    if "permissions" in existing_tables:
        now = datetime.now()
        for pdef in CLAIM_PERMISSIONS:
            existing_id = conn.execute(
                sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == pdef["code"])
            ).scalar_one_or_none()

            if existing_id is None:
                conn.execute(
                    PERMISSIONS.insert(),
                    [
                        {
                            "code": pdef["code"],
                            "description": pdef["description"],
                            "group": pdef["group"],
                            "last_modified": now,
                        }
                    ],
                )
                perm_id = conn.execute(
                    sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == pdef["code"])
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
                        conn.execute(ROLE_PERMISSIONS.insert().values(role_id=r_id, permission_id=perm_id))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    # 1. Revoke and delete permissions
    if "permissions" in existing_tables:
        for pdef in CLAIM_PERMISSIONS:
            code = pdef["code"]
            perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar_one_or_none()
            if perm_id is not None:
                if "role_permissions" in existing_tables:
                    conn.execute(sa.delete(ROLE_PERMISSIONS).where(ROLE_PERMISSIONS.c.permission_id == perm_id))
                conn.execute(sa.delete(PERMISSIONS).where(PERMISSIONS.c.id == perm_id))

    # 2. Drop warranty_claim_events
    if "warranty_claim_events" in existing_tables:
        op.drop_table("warranty_claim_events")

    # 3. Drop warranty_claims
    if "warranty_claims" in existing_tables:
        op.execute("DROP INDEX IF EXISTS uq_warranty_active_claim;")
        op.drop_table("warranty_claims")
