"""add_stock_count_tables

Revision ID: a1192181b3ab
Revises: 74b1759042ea
Create Date: 2026-02-28 16:40:24.958005

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1192181b3ab"
down_revision: Union[str, None] = "74b1759042ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_counts",
        sa.Column("id", sa.Integer(), sa.ForeignKey("documents.id"), primary_key=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("total_variance_value", sa.Numeric(12, 2), server_default="0"),
    )

    op.create_table(
        "stock_count_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stock_count_id", sa.Integer(), sa.ForeignKey("stock_counts.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("expected_qty", sa.Numeric(10, 3), nullable=False),
        sa.Column("counted_qty", sa.Numeric(10, 3), nullable=True),
        sa.Column("variance_qty", sa.Numeric(10, 3), nullable=True),
        sa.Column("variance_value", sa.Numeric(12, 2), nullable=True),
    )
    op.create_index("ix_stock_count_items_stock_count_id", "stock_count_items", ["stock_count_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_count_items_stock_count_id", "stock_count_items")
    op.drop_table("stock_count_items")
    op.drop_table("stock_counts")
