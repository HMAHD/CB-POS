"""add autosave to suspended transactions (Issue #932)

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-11-20 12:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "suspended_transactions" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("suspended_transactions")}
        with op.batch_alter_table("suspended_transactions", schema=None) as batch_op:
            if "is_autosave" not in existing_cols:
                batch_op.add_column(sa.Column("is_autosave", sa.Boolean(), server_default=sa.false(), nullable=False))
            if "terminal_id" not in existing_cols:
                batch_op.add_column(sa.Column("terminal_id", sa.String(length=50), nullable=True))
            if "revision" not in existing_cols:
                batch_op.add_column(sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
            batch_op.alter_column("data", existing_type=sa.String(), nullable=True)

        existing_indexes = {idx["name"] for idx in insp.get_indexes("suspended_transactions")}
        if "ix_suspended_transactions_terminal_id" not in existing_indexes:
            op.create_index(
                "ix_suspended_transactions_terminal_id",
                "suspended_transactions",
                ["terminal_id"],
            )

        if "uq_suspended_transactions_autosave_terminal" not in existing_indexes:
            op.create_index(
                "uq_suspended_transactions_autosave_terminal",
                "suspended_transactions",
                ["terminal_id"],
                unique=True,
                sqlite_where=sa.text("is_autosave = 1"),
                postgresql_where=sa.text("is_autosave IS TRUE"),
            )

    # Safe compatibility data migration for existing configured shops (Decision D36)
    if "feature_flags" in existing_tables:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM feature_flags")).scalar()
        if count and count > 0:
            existing_flag = conn.execute(
                sa.text("SELECT 1 FROM feature_flags WHERE name = 'power_cut_autosave'")
            ).scalar()
            if not existing_flag:
                feature_flags_table = sa.table(
                    "feature_flags",
                    sa.column("name", sa.String),
                    sa.column("enabled", sa.Boolean),
                    sa.column("last_modified", sa.DateTime),
                )
                conn.execute(
                    sa.insert(feature_flags_table).values(
                        name="power_cut_autosave",
                        enabled=True,
                        last_modified=sa.func.now(),
                    )
                )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "suspended_transactions" in existing_tables:
        existing_indexes = {idx["name"] for idx in insp.get_indexes("suspended_transactions")}
        if "uq_suspended_transactions_autosave_terminal" in existing_indexes:
            op.drop_index("uq_suspended_transactions_autosave_terminal", table_name="suspended_transactions")
        if "ix_suspended_transactions_terminal_id" in existing_indexes:
            op.drop_index("ix_suspended_transactions_terminal_id", table_name="suspended_transactions")

        with op.batch_alter_table("suspended_transactions", schema=None) as batch_op:
            batch_op.drop_column("revision")
            batch_op.drop_column("terminal_id")
            batch_op.drop_column("is_autosave")
            batch_op.alter_column("data", existing_type=sa.String(), nullable=False)

    if "feature_flags" in existing_tables:
        conn.execute(sa.text("DELETE FROM feature_flags WHERE name = 'power_cut_autosave'"))
