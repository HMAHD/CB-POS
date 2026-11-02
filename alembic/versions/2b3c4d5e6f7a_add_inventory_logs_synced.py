"""add synced to inventory_logs (#903)

Revision ID: 2b3c4d5e6f7a
Revises: 1f2e3d4c5b6a
Create Date: 2026-11-03 01:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b3c4d5e6f7a"
down_revision: Union[str, None] = "1f2e3d4c5b6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "inventory_logs" not in existing_tables:
        op.create_table(
            "inventory_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("qty_change", sa.Numeric(precision=10, scale=3), nullable=False),
            sa.Column("new_qty", sa.Numeric(precision=10, scale=3), nullable=False),
            sa.Column("reason", sa.String(length=200), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
            sa.Column("synced", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_inventory_logs_synced", "inventory_logs", ["synced"], unique=False)
    else:
        existing_cols = {col["name"] for col in insp.get_columns("inventory_logs")}
        with op.batch_alter_table("inventory_logs", schema=None) as batch_op:
            if "synced" not in existing_cols:
                batch_op.add_column(sa.Column("synced", sa.Boolean(), nullable=False, server_default=sa.false()))
                batch_op.create_index("ix_inventory_logs_synced", ["synced"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    if "inventory_logs" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("inventory_logs")}
        if "synced" in existing_cols:
            with op.batch_alter_table("inventory_logs", schema=None) as batch_op:
                batch_op.drop_index("ix_inventory_logs_synced")
                batch_op.drop_column("synced")
