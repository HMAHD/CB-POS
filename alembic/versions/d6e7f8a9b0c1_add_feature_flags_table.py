"""add feature flags table (Issue #942)

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-20 10:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "feature_flags" not in existing_tables:
        op.create_table(
            "feature_flags",
            sa.Column("name", sa.String(length=50), primary_key=True, nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("last_modified", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index("ix_feature_flags_last_modified", "feature_flags", ["last_modified"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "feature_flags" in existing_tables:
        op.drop_index("ix_feature_flags_last_modified", table_name="feature_flags")
        op.drop_table("feature_flags")
