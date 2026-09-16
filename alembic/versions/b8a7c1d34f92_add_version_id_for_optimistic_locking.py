"""add_version_id_for_optimistic_locking

Revision ID: b8a7c1d34f92
Revises: 0e120b28c005
Create Date: 2026-02-18 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b8a7c1d34f92"
down_revision = "0e120b28c005"
branch_labels = None
depends_on = None


def upgrade():
    # Add version_id column to products table for optimistic locking
    op.add_column("products", sa.Column("version_id", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    # Remove version_id column
    op.drop_column("products", "version_id")
