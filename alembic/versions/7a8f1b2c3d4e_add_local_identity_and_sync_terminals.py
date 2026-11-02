"""add local_identity and sync_terminals tables and origin_db_instance_id to sync_id_map (#866)

Revision ID: 7a8f1b2c3d4e
Revises: e9f2a1b4c803
Create Date: 2026-11-02 16:00:00.000000

"""

import uuid
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a8f1b2c3d4e"
down_revision: Union[str, None] = "e9f2a1b4c803"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create local_identity table
    op.create_table(
        "local_identity",
        sa.Column("db_instance_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("db_instance_id"),
    )

    # Seed with fresh UUID for existing database
    conn = op.get_bind()
    local_identity_table = sa.table(
        "local_identity",
        sa.column("db_instance_id", sa.String),
    )
    op.bulk_insert(local_identity_table, [{"db_instance_id": str(uuid.uuid4())}])

    # 2. Create sync_terminals table
    op.create_table(
        "sync_terminals",
        sa.Column("terminal_id", sa.String(length=50), nullable=False),
        sa.Column("db_instance_id", sa.String(length=36), nullable=False),
        sa.Column("first_seen", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_ip", sa.String(length=50), nullable=True),
        sa.Column("released", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("terminal_id"),
    )

    # 3. Alter sync_id_map to include origin_db_instance_id and update unique constraint
    insp = sa.inspect(conn)
    tables = insp.get_table_names()
    if "sync_id_map" in tables:
        with op.batch_alter_table("sync_id_map", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("origin_db_instance_id", sa.String(length=36), nullable=False, server_default="legacy")
            )
            batch_op.drop_constraint("uq_sync_id_map_origin_local", type_="unique")
            batch_op.create_unique_constraint(
                "uq_sync_id_map_origin_instance_local",
                ["origin_terminal_id", "origin_db_instance_id", "table_name", "local_id"],
            )
    else:
        op.create_table(
            "sync_id_map",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("origin_terminal_id", sa.String(length=50), nullable=False),
            sa.Column("origin_db_instance_id", sa.String(length=36), nullable=False, server_default="legacy"),
            sa.Column("table_name", sa.String(length=50), nullable=False),
            sa.Column("local_id", sa.Integer(), nullable=False),
            sa.Column("server_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "origin_terminal_id",
                "origin_db_instance_id",
                "table_name",
                "local_id",
                name="uq_sync_id_map_origin_instance_local",
            ),
        )
        with op.batch_alter_table("sync_id_map", schema=None) as batch_op:
            batch_op.create_index("ix_sync_id_map_table_server", ["table_name", "server_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sync_id_map", schema=None) as batch_op:
        batch_op.drop_constraint("uq_sync_id_map_origin_instance_local", type_="unique")
        batch_op.create_unique_constraint(
            "uq_sync_id_map_origin_local",
            ["origin_terminal_id", "table_name", "local_id"],
        )
        batch_op.drop_column("origin_db_instance_id")

    op.drop_table("sync_terminals")
    op.drop_table("local_identity")
