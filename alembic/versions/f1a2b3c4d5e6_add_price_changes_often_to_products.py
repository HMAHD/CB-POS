"""add price_changes_often to products (Issue #931)

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-11-21 10:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "products" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("products")}
        with op.batch_alter_table("products", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "price_changes_often" not in existing_cols:
                batch_op.add_column(
                    sa.Column("price_changes_often", sa.Boolean(), server_default=sa.false(), nullable=False)
                )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "products" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("products")}
        with op.batch_alter_table("products", reflect_kwargs={"resolve_fks": False}) as batch_op:
            if "price_changes_often" in existing_cols:
                batch_op.drop_column("price_changes_often")
