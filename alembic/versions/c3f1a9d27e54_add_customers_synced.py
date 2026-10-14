"""add customers.synced

Revision ID: c3f1a9d27e54
Revises: e177823b8aa9
Create Date: 2026-10-14 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f1a9d27e54"
down_revision: Union[str, None] = "e177823b8aa9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# LAN Sync (#680): a customer created on a till is pushed to the Main PC
# once (synced = false until the Main PC has it). Customers that already
# exist are marked synced: on a till they came from the Main PC, and on a
# Main PC or standalone install there is nothing to push.


def upgrade() -> None:
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("synced", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_column("synced")
