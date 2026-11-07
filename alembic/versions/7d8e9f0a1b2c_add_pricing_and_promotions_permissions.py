"""add pricing and promotions permissions (Issue #858)

Revision ID: 7d8e9f0a1b2c
Revises: 61b23204d804
Create Date: 2026-11-07 11:30:00.000000

"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d8e9f0a1b2c"
down_revision: Union[str, None] = "61b23204d804"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSIONS = (
    ("pricing.manage", "Pricing Manage"),
    ("promotions.manage", "Promotions Manage"),
)
GROUP = "Inventory"

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
CODES = [code for code, _ in NEW_PERMISSIONS]


def upgrade() -> None:
    conn = op.get_bind()
    existing = set(conn.execute(sa.select(PERMISSIONS.c.code).where(PERMISSIONS.c.code.in_(CODES))).scalars())
    missing = [
        {"code": code, "description": description, "group": GROUP, "last_modified": datetime.now()}
        for code, description in NEW_PERMISSIONS
        if code not in existing
    ]
    if missing:
        conn.execute(PERMISSIONS.insert(), missing)

    perm_ids = list(conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code.in_(CODES))).scalars())

    # Grant to roles named admin, manager or any role currently holding admin.manage_users
    admin_manage_users_id = conn.execute(
        sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == "admin.manage_users")
    ).scalar_one_or_none()

    role_id_query = sa.select(ROLES.c.id).where(sa.func.lower(ROLES.c.name).in_(("admin", "manager")))
    target_role_ids = set(conn.execute(role_id_query).scalars())

    if admin_manage_users_id is not None:
        holders = conn.execute(
            sa.select(ROLE_PERMISSIONS.c.role_id).where(ROLE_PERMISSIONS.c.permission_id == admin_manage_users_id)
        ).scalars()
        target_role_ids.update(holders)

    granted = set(
        conn.execute(
            sa.select(ROLE_PERMISSIONS.c.role_id, ROLE_PERMISSIONS.c.permission_id).where(
                ROLE_PERMISSIONS.c.permission_id.in_(perm_ids)
            )
        ).all()
    )

    rows = [
        {"role_id": role_id, "permission_id": perm_id}
        for role_id in target_role_ids
        for perm_id in perm_ids
        if (role_id, perm_id) not in granted
    ]
    if rows:
        conn.execute(ROLE_PERMISSIONS.insert(), rows)


def downgrade() -> None:
    conn = op.get_bind()
    perm_ids = sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code.in_(CODES))
    conn.execute(ROLE_PERMISSIONS.delete().where(ROLE_PERMISSIONS.c.permission_id.in_(perm_ids)))
    conn.execute(PERMISSIONS.delete().where(PERMISSIONS.c.code.in_(CODES)))
