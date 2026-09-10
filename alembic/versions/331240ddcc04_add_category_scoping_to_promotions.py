"""add category scoping to promotions

Revision ID: 331240ddcc04
Revises: 91ce190ffa8b
Create Date: 2026-09-10 10:38:43.313923

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "331240ddcc04"
down_revision: Union[str, None] = "91ce190ffa8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("promotions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_promotions_category_id"), ["category_id"], unique=False)
        batch_op.create_foreign_key("fk_promotions_category_id", "categories", ["category_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("promotions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_promotions_category_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_promotions_category_id"))
        batch_op.drop_column("category_id")
