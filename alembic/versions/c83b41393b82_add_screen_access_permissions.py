"""add screen access permissions

Revision ID: c83b41393b82
Revises: c3f1a9d27e54
Create Date: 2026-10-14 15:00:00.000000

"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c83b41393b82"
down_revision: Union[str, None] = "c3f1a9d27e54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The side menu used to show Management and Settings to any role *named*
# admin/manager/owner (#549). It now checks the management.view /
# settings.view permissions instead. So nobody loses access on upgrade,
# both are granted to exactly the roles the old name check let in.
# New installs get them via Permissions.get_groups() at first-run setup.
NEW_PERMISSIONS = (
    ("management.view", "Management View"),
    ("settings.view", "Settings View"),
)
GROUP = "Screens"
ROLE_NAMES_WITH_ACCESS = ("admin", "manager", "owner")

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
        op.bulk_insert(PERMISSIONS, missing)

    perm_ids = list(conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code.in_(CODES))).scalars())
    role_ids = list(
        conn.execute(sa.select(ROLES.c.id).where(sa.func.lower(ROLES.c.name).in_(ROLE_NAMES_WITH_ACCESS))).scalars()
    )
    granted = set(
        conn.execute(
            sa.select(ROLE_PERMISSIONS.c.role_id, ROLE_PERMISSIONS.c.permission_id).where(
                ROLE_PERMISSIONS.c.permission_id.in_(perm_ids)
            )
        ).all()
    )
    rows = [
        {"role_id": role_id, "permission_id": perm_id}
        for role_id in role_ids
        for perm_id in perm_ids
        if (role_id, perm_id) not in granted
    ]
    if rows:
        op.bulk_insert(ROLE_PERMISSIONS, rows)


def downgrade() -> None:
    perm_ids = sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code.in_(CODES))
    op.execute(ROLE_PERMISSIONS.delete().where(ROLE_PERMISSIONS.c.permission_id.in_(perm_ids)))
    op.execute(PERMISSIONS.delete().where(PERMISSIONS.c.code.in_(CODES)))
