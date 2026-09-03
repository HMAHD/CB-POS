"""add sync columns and sync tables for multi-terminal LAN sync

Revision ID: 91ce190ffa8b
Revises: de0680f959ba
Create Date: 2026-09-02 23:34:21.483983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91ce190ffa8b'
down_revision: Union[str, None] = 'de0680f959ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- New tables ---
    op.create_table('sync_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('terminal_id', sa.String(length=50), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('sync_type', sa.String(length=30), nullable=False),
    sa.Column('records_count', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sync_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sync_logs_terminal_id'), ['terminal_id'], unique=False)

    op.create_table('sync_queue',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('table_name', sa.String(length=50), nullable=False),
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=10), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sync_queue', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sync_queue_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_sync_queue_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_sync_queue_table_name'), ['table_name'], unique=False)

    # --- synced columns (Boolean NOT NULL, default False) ---
    # server_default='0' is required for SQLite ALTER TABLE on existing rows.
    _synced_tables = [
        'audit_logs', 'cash_movements', 'customer_ledger',
        'customer_payments', 'shifts', 'stock_movements',
        'supplier_ledger', 'supplier_payments',
    ]
    for table in _synced_tables:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('synced', sa.Boolean(), nullable=False, server_default='0'))
            batch_op.create_index(batch_op.f(f'ix_{table}_synced'), ['synced'], unique=False)

    # documents gets synced + origin_terminal_id
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origin_terminal_id', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('synced', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.create_index(batch_op.f('ix_documents_origin_terminal_id'), ['origin_terminal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documents_synced'), ['synced'], unique=False)

    # --- last_modified columns (DateTime NOT NULL, default now) ---
    _now = sa.func.now()
    _catalog_tables = [
        'categories', 'customers', 'payment_methods', 'permissions',
        'price_lists', 'products', 'promotions', 'roles',
        'suppliers', 'units', 'users', 'void_reasons',
    ]
    for table in _catalog_tables:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('last_modified', sa.DateTime(), nullable=False, server_default=_now))
            batch_op.create_index(batch_op.f(f'ix_{table}_last_modified'), ['last_modified'], unique=False)


def downgrade() -> None:
    # --- Remove last_modified from catalog tables ---
    _catalog_tables = [
        'void_reasons', 'users', 'units', 'suppliers', 'roles',
        'promotions', 'products', 'price_lists', 'permissions',
        'payment_methods', 'customers', 'categories',
    ]
    for table in _catalog_tables:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f'ix_{table}_last_modified'))
            batch_op.drop_column('last_modified')

    # --- Remove synced + origin_terminal_id from documents ---
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documents_synced'))
        batch_op.drop_index(batch_op.f('ix_documents_origin_terminal_id'))
        batch_op.drop_column('synced')
        batch_op.drop_column('origin_terminal_id')

    # --- Remove synced from transaction tables ---
    _synced_tables = [
        'supplier_payments', 'supplier_ledger', 'stock_movements',
        'shifts', 'customer_payments', 'customer_ledger',
        'cash_movements', 'audit_logs',
    ]
    for table in _synced_tables:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f'ix_{table}_synced'))
            batch_op.drop_column('synced')

    # --- Drop new tables ---
    with op.batch_alter_table('sync_queue', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sync_queue_table_name'))
        batch_op.drop_index(batch_op.f('ix_sync_queue_status'))
        batch_op.drop_index(batch_op.f('ix_sync_queue_created_at'))
    op.drop_table('sync_queue')

    with op.batch_alter_table('sync_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sync_logs_terminal_id'))
    op.drop_table('sync_logs')
