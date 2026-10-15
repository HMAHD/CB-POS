"""add loyalty adjust permission

Revision ID: e5f8a1c9b204
Revises: d4e7b2a9c816
Create Date: 2026-10-15 17:30:00.000000

"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f8a1c9b204"
down_revision: Union[str, None] = "d4e7b2a9c816"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSION = ("loyalty.adjust_points", "Loyalty Adjust Points", "Loyalty")
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
    conn = op.get_bind()
    code, description, group = NEW_PERMISSION

    existing = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar()
    if existing is None:
        op.bulk_insert(
            PERMISSIONS,
            [{"code": code, "description": description, "group": group, "last_modified": datetime.now()}],
        )
        perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar()
    else:
        perm_id = existing

    role_ids = list(
        conn.execute(sa.select(ROLES.c.id).where(sa.func.lower(ROLES.c.name).in_(ROLE_NAMES_WITH_ACCESS))).scalars()
    )
    granted = set(
        conn.execute(
            sa.select(ROLE_PERMISSIONS.c.role_id, ROLE_PERMISSIONS.c.permission_id).where(
                ROLE_PERMISSIONS.c.permission_id == perm_id
            )
        ).all()
    )
    rows = [{"role_id": role_id, "permission_id": perm_id} for role_id in role_ids if (role_id, perm_id) not in granted]
    if rows:
        op.bulk_insert(ROLE_PERMISSIONS, rows)


def downgrade() -> None:
    conn = op.get_bind()
    code = NEW_PERMISSION[0]
    perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar()
    if perm_id is not None:
        op.execute(ROLE_PERMISSIONS.delete().where(ROLE_PERMISSIONS.c.permission_id == perm_id))
        op.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id == perm_id))
