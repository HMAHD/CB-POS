"""audit permission catalogue, remove inventory.delete and grant inventory.view and purchase.view

Revision ID: 8e9f0a1b2c3d
Revises: 7d8e9f0a1b2c
Create Date: 2026-11-07
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "8e9f0a1b2c3d"
down_revision = "7d8e9f0a1b2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Foreign-key safe deletion: delete associations first
    conn.execute(
        sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'inventory.delete')
    """)
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'inventory.delete'"))

    # 2. Idempotent grant of inventory.view and purchase.view to all roles holding management.view
    conn.execute(
        sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT DISTINCT r.id, p.id
        FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p_mgmt ON p_mgmt.id = rp.permission_id AND p_mgmt.code = 'management.view'
        CROSS JOIN permissions p
        WHERE p.code IN ('inventory.view', 'purchase.view')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp2
              WHERE rp2.role_id = r.id AND rp2.permission_id = p.id
          )
    """)
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Re-insert inventory.delete
    res = conn.execute(sa.text("SELECT id FROM permissions WHERE code = 'inventory.delete'")).scalar_one_or_none()
    if not res:
        now = datetime.now(UTC)
        conn.execute(
            sa.text("""
            INSERT INTO permissions (code, description, "group", last_modified)
            VALUES ('inventory.delete', 'Delete products', 'Inventory', :now)
        """),
            {"now": now},
        )
        perm_id = conn.execute(sa.text("SELECT id FROM permissions WHERE code = 'inventory.delete'")).scalar_one()
        admin_role_id = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'Admin'")).scalar_one_or_none()
        if admin_role_id:
            conn.execute(
                sa.text(f"INSERT INTO role_permissions (role_id, permission_id) VALUES ({admin_role_id}, {perm_id})")
            )
