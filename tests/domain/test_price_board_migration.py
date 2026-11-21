"""Tests for Alembic migration f1a2b3c4d5e6 (price_changes_often on products #931)."""

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect

from alembic import command
from cbpos.config import Config
from cbpos.core.database import Base


@pytest.fixture
def alembic_cfg(tmp_path, monkeypatch):
    db_path = tmp_path / "test_migration_price_board.db"
    uri = f"sqlite:///{db_path}"
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", uri)

    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", uri)
    cfg.attributes["configure_logger"] = False
    return cfg, uri, db_path


@pytest.mark.domain
def test_price_changes_often_migration_upgrade_and_downgrade(alembic_cfg):
    cfg, uri, _ = alembic_cfg

    engine = create_engine(uri)
    Base.metadata.create_all(engine)

    # Stamp head and downgrade to e7f8a9b0c1d2
    command.stamp(cfg, "head")
    command.downgrade(cfg, "e7f8a9b0c1d2")

    insp_down = inspect(engine)
    cols_down = {col["name"] for col in insp_down.get_columns("products")}
    assert "price_changes_often" not in cols_down

    # Upgrade to head (f1a2b3c4d5e6)
    command.upgrade(cfg, "head")

    insp_up = inspect(engine)
    cols_up = {col["name"] for col in insp_up.get_columns("products")}
    assert "price_changes_often" in cols_up

    # Downgrade again
    command.downgrade(cfg, "e7f8a9b0c1d2")
    insp_down2 = inspect(engine)
    cols_down2 = {col["name"] for col in insp_down2.get_columns("products")}
    assert "price_changes_often" not in cols_down2
