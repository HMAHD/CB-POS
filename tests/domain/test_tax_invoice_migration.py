"""Tests for Alembic migration d4e5f6a7b8c9 (Tax Invoice tables and permission)."""

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect, text

from alembic import command
from cbpos.config import Config


@pytest.fixture
def alembic_cfg(tmp_path, monkeypatch):
    db_path = tmp_path / "test_migration.db"
    uri = f"sqlite:///{db_path}"
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", uri)

    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", uri)
    cfg.attributes["configure_logger"] = False
    return cfg, uri, db_path


def test_tax_invoice_migration_upgrade_and_downgrade(alembic_cfg):
    cfg, uri, _ = alembic_cfg

    # 1. Create base tables, seed roles, and stamp at head
    engine = create_engine(uri)
    from cbpos.core.database import Base

    Base.metadata.create_all(engine)

    with engine.connect() as conn:
        # Seed test admin and manager roles if roles table exists
        insp = inspect(conn)
        if "roles" in insp.get_table_names():
            conn.execute(
                text(
                    "INSERT INTO roles (name, access_level, last_modified) "
                    "VALUES ('Admin', 9, CURRENT_TIMESTAMP), ('Manager', 5, CURRENT_TIMESTAMP)"
                )
            )
            conn.commit()

    # Stamp head and downgrade our new migration to c3d4e5f6a7b8
    command.stamp(cfg, "head")
    command.downgrade(cfg, "c3d4e5f6a7b8")

    # Verify tables do not exist before upgrade
    insp = inspect(engine)
    tables_before = insp.get_table_names()
    assert "tax_invoices" not in tables_before
    assert "tax_invoice_lines" not in tables_before
    assert "tax_invoice_sequences" not in tables_before
    assert "tax_credit_notes" not in tables_before

    with engine.connect() as conn:
        perm_before = conn.execute(text("SELECT id FROM permissions WHERE code = 'sales.tax_invoice'")).fetchone()
        assert perm_before is None

    # 2. Upgrade to tax invoice migration (head)
    command.upgrade(cfg, "head")

    # 3. Verify tables and columns
    insp = inspect(engine)
    tables = insp.get_table_names()
    assert "tax_invoices" in tables
    assert "tax_invoice_lines" in tables
    assert "tax_invoice_sequences" in tables
    assert "tax_credit_notes" in tables

    ti_cols = {c["name"] for c in insp.get_columns("tax_invoices")}
    assert "serial" in ti_cols
    assert "supply_date" in ti_cols
    assert "supplier_tin" in ti_cols
    assert "buyer_tin" in ti_cols
    assert "print_count" in ti_cols
    assert "amount_in_words" in ti_cols

    line_cols = {c["name"] for c in insp.get_columns("tax_invoice_lines")}
    assert "tax_invoice_id" in line_cols
    assert "unit_snapshot" in line_cols
    assert "net_amount" in line_cols
    assert "vat_amount" in line_cols

    # Verify permission was seeded
    with engine.connect() as conn:
        perm_row = conn.execute(
            text("SELECT id, code, [group] FROM permissions WHERE code = 'sales.tax_invoice'")
        ).fetchone()
        assert perm_row is not None
        perm_id = perm_row[0]

        # Verify Admin & Manager roles have the permission
        grants = conn.execute(
            text("SELECT role_id FROM role_permissions WHERE permission_id = :pid"),
            {"pid": perm_id},
        ).fetchall()
        assert len(grants) >= 2

    # 4. Downgrade to previous head
    command.downgrade(cfg, "c3d4e5f6a7b8")

    insp = inspect(engine)
    tables_after = insp.get_table_names()
    assert "tax_invoices" not in tables_after
    assert "tax_invoice_lines" not in tables_after
    assert "tax_invoice_sequences" not in tables_after
    assert "tax_credit_notes" not in tables_after

    with engine.connect() as conn:
        perm_after = conn.execute(text("SELECT id FROM permissions WHERE code = 'sales.tax_invoice'")).fetchone()
        assert perm_after is None

    # 5. Re-upgrade to head works cleanly
    command.upgrade(cfg, "head")
    insp_final = inspect(engine)
    assert "tax_invoices" in insp_final.get_table_names()
    engine.dispose()
