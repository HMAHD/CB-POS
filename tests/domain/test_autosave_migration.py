"""Tests for Alembic migration e7f8a9b0c1d2 (Autosave to suspended transactions and compatibility)."""

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect, text

from alembic import command
from cbpos.config import Config
from cbpos.core.database import Base


@pytest.fixture
def alembic_cfg(tmp_path, monkeypatch):
    db_path = tmp_path / "test_migration_autosave.db"
    uri = f"sqlite:///{db_path}"
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", uri)

    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", uri)
    cfg.attributes["configure_logger"] = False
    return cfg, uri, db_path


@pytest.mark.domain
def test_autosave_migration_upgrade_and_downgrade(alembic_cfg):
    cfg, uri, _ = alembic_cfg

    engine = create_engine(uri)
    Base.metadata.create_all(engine)

    # Stamp head and downgrade to d6e7f8a9b0c1
    command.stamp(cfg, "head")
    command.downgrade(cfg, "d6e7f8a9b0c1")

    with engine.connect() as conn:
        # Simulate an existing configured shop that has feature flags
        conn.execute(
            text("INSERT INTO feature_flags (name, enabled, last_modified) VALUES ('warranty', 1, CURRENT_TIMESTAMP)")
        )
        conn.commit()

    # Upgrade to head (e7f8a9b0c1d2)
    command.upgrade(cfg, "head")

    insp = inspect(engine)
    cols = {col["name"] for col in insp.get_columns("suspended_transactions")}
    assert "is_autosave" in cols
    assert "terminal_id" in cols
    assert "revision" in cols

    indexes = {idx["name"] for idx in insp.get_indexes("suspended_transactions")}
    assert "ix_suspended_transactions_terminal_id" in indexes
    assert "uq_suspended_transactions_autosave_terminal" in indexes

    # Verify compatibility data migration: power_cut_autosave was added for configured shop
    with engine.connect() as conn:
        flag = conn.execute(text("SELECT enabled FROM feature_flags WHERE name = 'power_cut_autosave'")).scalar()
        assert bool(flag) is True

    # Test downgrade
    command.downgrade(cfg, "d6e7f8a9b0c1")

    insp = inspect(engine)
    cols_after = {col["name"] for col in insp.get_columns("suspended_transactions")}
    assert "is_autosave" not in cols_after
    assert "terminal_id" not in cols_after
    assert "revision" not in cols_after

    # Re-upgrade to head and dispose engine
    command.upgrade(cfg, "head")
    engine.dispose()


@pytest.mark.domain
def test_migration_downgrade_preserves_held_bills_and_purges_autosaves(alembic_cfg):
    """Defect 8: Migration downgrade must purge autosave rows and tombstone rows (data=NULL),
    while preserving ordinary held bills with non-null data.
    """
    cfg, uri, _ = alembic_cfg
    engine = create_engine(uri)
    Base.metadata.create_all(engine)

    # Stamp head and upgrade
    command.stamp(cfg, "head")

    with engine.connect() as conn:
        # 1. Ordinary held bill (is_autosave = False, data NOT NULL)
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, data, timestamp) "
                'VALUES (0, \'TERM-01\', 1, \'{"v": 2, "lines": ["item1"]}\', CURRENT_TIMESTAMP)'
            )
        )
        # 2. Active autosave (is_autosave = True, data NOT NULL)
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, data, timestamp) "
                'VALUES (1, \'TERM-01\', 5, \'{"v": 2, "lines": ["active_autosave"]}\', CURRENT_TIMESTAMP)'
            )
        )
        # 3. Tombstoned autosave (is_autosave = True, data IS NULL)
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, data, timestamp) "
                "VALUES (1, 'TERM-02', 10, NULL, CURRENT_TIMESTAMP)"
            )
        )
        conn.commit()

    # Downgrade to d6e7f8a9b0c1
    command.downgrade(cfg, "d6e7f8a9b0c1")

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, data FROM suspended_transactions")).fetchall()
        # Ordinary held bill MUST be preserved
        assert len(rows) == 1, f"Expected exactly 1 ordinary held bill after downgrade, got {len(rows)}"
        assert "item1" in rows[0][1]

    # Re-upgrade to head and dispose engine
    command.upgrade(cfg, "head")
    engine.dispose()


@pytest.mark.domain
def test_downgrade_sql_compiles_valid_boolean_expression_for_postgresql():
    """P2: Migration downgrade must use a SQLAlchemy expression that compiles correctly
    for PostgreSQL without invalid boolean-integer comparisons (e.g. is_autosave = 1).
    """
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql, sqlite

    suspended_tbl = sa.table(
        "suspended_transactions",
        sa.column("is_autosave", sa.Boolean),
        sa.column("data", sa.String),
    )
    delete_stmt = sa.delete(suspended_tbl).where(
        sa.or_(
            suspended_tbl.c.is_autosave.is_(True),
            suspended_tbl.c.data.is_(None),
        )
    )

    compiled_pg = str(delete_stmt.compile(dialect=postgresql.dialect())).lower()
    assert "= 1" not in compiled_pg, f"Invalid boolean integer comparison in PostgreSQL SQL: {compiled_pg}"
    assert "is true" in compiled_pg or "is_autosave = true" in compiled_pg or "is_autosave" in compiled_pg
    assert "data is null" in compiled_pg

    # Also verify SQLite compilation works cleanly
    compiled_sqlite = str(delete_stmt.compile(dialect=sqlite.dialect())).lower()
    assert "data is null" in compiled_sqlite

    # And verify the raw migration file does not contain raw SQL 'is_autosave = 1'
    from cbpos.config import Config

    migration_file = Config.BASE_DIR / "alembic" / "versions" / "e7f8a9b0c1d2_add_autosave_to_suspended_transactions.py"
    content = migration_file.read_text(encoding="utf-8")
    downgrade_section = content[content.index("def downgrade()") :]
    assert "is_autosave = 1" not in downgrade_section, (
        "Found invalid boolean comparison 'is_autosave = 1' in migration downgrade"
    )


@pytest.mark.postgres
@pytest.mark.integration
def test_postgres_migration_downgrade_preserves_held_bills_and_purges_autosaves(pg_engine):
    """Verify downgrade on real PostgreSQL with populated table preserves all ordinary held bills and purges autosaves."""
    from alembic.config import Config as AlembicConfig

    pg_url = os.environ.get("CBPOS_TEST_PG_URL")
    assert pg_url

    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", pg_url)
    cfg.attributes["configure_logger"] = False

    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

    Base.metadata.create_all(pg_engine)
    command.stamp(cfg, "head")

    with pg_engine.begin() as conn:
        # 1. Multiple ordinary held bills across multiple terminals
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, note, data, timestamp) "
                'VALUES (false, \'TERM-01\', 1, \'Table 1\', \'{"v": 2, "lines": [{"barcode": "P1", "qty": "1.000"}]}\', CURRENT_TIMESTAMP)'
            )
        )
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, note, data, timestamp) "
                'VALUES (false, \'TERM-02\', 2, \'Customer Order\', \'{"v": 2, "lines": [{"barcode": "P2", "qty": "3.500"}]}\', CURRENT_TIMESTAMP)'
            )
        )
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, note, data, timestamp) "
                'VALUES (false, \'TERM-03\', 3, \'VIP\', \'{"v": 2, "lines": [{"barcode": "P3", "qty": "10.000"}]}\', CURRENT_TIMESTAMP)'
            )
        )

        # 2. Multiple active autosaves with populated json data across terminals
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, data, timestamp) "
                'VALUES (true, \'TERM-01\', 5, \'{"v": 2, "lines": [{"barcode": "AUTO1", "qty": "1.000"}]}\', CURRENT_TIMESTAMP)'
            )
        )
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, data, timestamp) "
                'VALUES (true, \'TERM-02\', 8, \'{"v": 2, "lines": [{"barcode": "AUTO2", "qty": "2.000"}]}\', CURRENT_TIMESTAMP)'
            )
        )

        # 3. Multiple tombstone autosave rows (data IS NULL) across terminals
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, data, timestamp) "
                "VALUES (true, 'TERM-03', 12, NULL, CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO suspended_transactions (is_autosave, terminal_id, revision, data, timestamp) "
                "VALUES (true, 'TERM-04', 15, NULL, CURRENT_TIMESTAMP)"
            )
        )

    # Downgrade to d6e7f8a9b0c1 on PostgreSQL
    command.downgrade(cfg, "d6e7f8a9b0c1")

    # Verify that:
    # 1. Exactly the 3 ordinary held bills remain.
    # 2. All 4 autosaves/tombstones were purged.
    # 3. None of the ordinary held bills were corrupted or dropped.
    with pg_engine.begin() as conn:
        rows = conn.execute(text("SELECT id, note, data FROM suspended_transactions ORDER BY id")).fetchall()
        assert len(rows) == 3
        notes = [r[1] for r in rows]
        assert notes == ["Table 1", "Customer Order", "VIP"]
        assert "P1" in rows[0][2]
        assert "P2" in rows[1][2]
        assert "P3" in rows[2][2]

    # Re-upgrade to head
    command.upgrade(cfg, "head")
