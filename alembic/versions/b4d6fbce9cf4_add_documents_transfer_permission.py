"""add documents transfer permission

Revision ID: b4d6fbce9cf4
Revises: 472d587b7bd7
Create Date: 2026-09-27 12:09:32.729432

"""

from collections.abc import Sequence
from datetime import datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d6fbce9cf4"
down_revision: Union[str, None] = "472d587b7bd7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# New installs get this via Permissions.get_groups() at first-run setup
# (which also stamps alembic head, so this never double-runs there);
# existing databases only ever gain new permission codes through a data
# migration like this one, since nothing else re-syncs the permissions
# table with the Permissions class at runtime (#479).
PERMISSIONS_TABLE = sa.table(
    "permissions",
    sa.column("code", sa.String),
    sa.column("description", sa.String),
    sa.column("group", sa.String),
    sa.column("last_modified", sa.DateTime),
)


def upgrade() -> None:
    op.bulk_insert(
        PERMISSIONS_TABLE,
        [
            {
                "code": "documents.transfer",
                "description": "Documents Transfer",
                "group": "Documents",
                "last_modified": datetime.now(),
            }
        ],
    )


def downgrade() -> None:
    op.execute(PERMISSIONS_TABLE.delete().where(PERMISSIONS_TABLE.c.code == "documents.transfer"))
