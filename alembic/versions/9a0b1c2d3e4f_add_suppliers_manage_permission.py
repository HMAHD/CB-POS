"""add suppliers.manage permission (Issue #896)

Revision ID: 9a0b1c2d3e4f
Revises: 8e9f0a1b2c3d
Create Date: 2026-11-07
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "9a0b1c2d3e4f"
down_revision = "8e9f0a1b2c3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Idempotently insert suppliers.manage into permissions
    res = conn.execute(sa.text("SELECT id FROM permissions WHERE code = 'suppliers.manage'")).scalar_one_or_none()
    if not res:
        now = datetime.now(UTC)
        conn.execute(
            sa.text("""
            INSERT INTO permissions (code, description, "group", last_modified)
            VALUES ('suppliers.manage', 'Manage suppliers (add, edit, deactivate)', 'Purchase', :now)
        """),
            {"now": now},
        )

    # 2. Grant to Admin, Manager, and all roles holding management.view
    conn.execute(
        sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT DISTINCT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE p.code = 'suppliers.manage'
          AND (
              LOWER(r.name) IN ('admin', 'manager')
              OR r.id IN (
                  SELECT rp.role_id
                  FROM role_permissions rp
                  JOIN permissions p_mgmt ON p_mgmt.id = rp.permission_id AND p_mgmt.code = 'management.view'
              )
          )
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp2
              WHERE rp2.role_id = r.id AND rp2.permission_id = p.id
          )
    """)
    )


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Remove role associations
    conn.execute(
        sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'suppliers.manage')
    """)
    )

    # 2. Remove permission
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'suppliers.manage'"))
