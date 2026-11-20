"""Tests for Alembic migration e7f8a9b0c1d2 (Autosave to suspended transactions and compatibility)."""

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

    # Re-upgrade to head and dispose engine
    command.upgrade(cfg, "head")
    engine.dispose()
