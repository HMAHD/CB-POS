"""add sales.reprint permission (Issue #911)

Revision ID: b2c3d4e5f6a7
Revises: 9a0b1c2d3e4f
Create Date: 2026-11-07 22:00:00.000000

"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "9a0b1c2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODE = "sales.reprint"
DESCRIPTION = "Reprint receipts"
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
    if "permissions" not in existing_tables:
        return

    existing_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == CODE)).scalar_one_or_none()
    if existing_id is None:
        conn.execute(
            PERMISSIONS.insert(),
            [{"code": CODE, "description": DESCRIPTION, "group": GROUP, "last_modified": datetime.now()}],
        )
        perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == CODE)).scalar_one_or_none()
    else:
        perm_id = existing_id

    if perm_id is None:
        return

    # Grant to roles named admin, manager, cashier or any role currently holding sales.view
    sales_view_id = conn.execute(
        sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == "sales.view")
    ).scalar_one_or_none()

    role_id_query = sa.select(ROLES.c.id).where(sa.func.lower(ROLES.c.name).in_(("admin", "manager", "cashier")))
    target_role_ids = set(conn.execute(role_id_query).scalars())

    if sales_view_id is not None:
        holders = conn.execute(
            sa.select(ROLE_PERMISSIONS.c.role_id).where(ROLE_PERMISSIONS.c.permission_id == sales_view_id)
        ).scalars()
        target_role_ids.update(holders)

    granted = set(
        conn.execute(sa.select(ROLE_PERMISSIONS.c.role_id).where(ROLE_PERMISSIONS.c.permission_id == perm_id)).scalars()
    )

    rows = [{"role_id": role_id, "permission_id": perm_id} for role_id in target_role_ids if role_id not in granted]
    if rows:
        conn.execute(ROLE_PERMISSIONS.insert(), rows)


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())
    if "permissions" not in existing_tables:
        return

    perm_id = conn.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == CODE)).scalar_one_or_none()
    if perm_id is not None:
        conn.execute(ROLE_PERMISSIONS.delete().where(ROLE_PERMISSIONS.c.permission_id == perm_id))
        conn.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id == perm_id))
