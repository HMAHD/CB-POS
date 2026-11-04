"""add sales shift_id and force close permission (#884)

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-11-04 02:00:00.000000

"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSION = ("shift.force_close", "Shift Force Close", "Cash")
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

    # 1. Add shift_id to sales table
    existing_tables = set(insp.get_table_names())
    if "sales" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("sales")}
        if "shift_id" not in existing_cols:
            with op.batch_alter_table("sales", schema=None) as batch_op:
                batch_op.add_column(sa.Column("shift_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key("fk_sales_shift_id", "shifts", ["shift_id"], ["id"])
                batch_op.create_index("ix_sales_shift_id", ["shift_id"], unique=False)

    # 2. Seed shift.force_close permission for Admin and Manager roles
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
    code, _, _ = NEW_PERMISSION
    perm_id = bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.code == code)).scalar()
    if perm_id is not None:
        op.execute(ROLE_PERMISSIONS.delete().where(ROLE_PERMISSIONS.c.permission_id == perm_id))
        op.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id == perm_id))

    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_index("ix_sales_shift_id")
        if bind.dialect.name != "sqlite":
            batch_op.drop_constraint("fk_sales_shift_id", type_="foreignkey")
        batch_op.drop_column("shift_id")
