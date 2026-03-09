"""add tax_id to customer

Revision ID: b41b19d9b69a
Revises: d1af69d5c525
Create Date: 2026-03-09 15:28:29.233382

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b41b19d9b69a"
down_revision: Union[str, None] = "d1af69d5c525"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tax_id", sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_column("tax_id")
