"""Startup schema migrations must run without logging.config and never fail silently (#630, UI-058).

PyInstaller bundles ``alembic/`` as data, so ``alembic/env.py``'s import of
``logging.config`` was never collected and every packaged migration died with
ImportError -- which ``run_migrations()`` only logged as a warning.
"""

import sqlite3
import sys

import pytest
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

import main
from alembic import command
from cbpos.config import Config
from cbpos.core.models import Base


def _script() -> ScriptDirectory:
    return ScriptDirectory(str(Config.BASE_DIR / "alembic"))


@pytest.fixture
def old_db(tmp_path, monkeypatch):
    """A DB at the real previous schema: create_all -> stamp head -> downgrade one step.

    Stamping an already-head schema one revision back would make the next
    schema-changing migration fail on "duplicate column", so actually run the
    head migration's downgrade instead.
    """
    db_path = tmp_path / "cbpos.db"
    uri = f"sqlite:///{db_path}"
    engine = create_engine(uri)
    Base.metadata.create_all(engine)
    engine.dispose()

    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", uri)

    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.stamp(cfg, "head")
    command.downgrade(cfg, "-1")
    return db_path


def _version(db_path) -> str:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_migration_runs_without_logging_config(old_db, monkeypatch):
    # Simulate the frozen build, where logging.config was never bundled.
    monkeypatch.setitem(sys.modules, "logging.config", None)

    assert main.run_migrations() is None
    assert _version(old_db) == _script().get_current_head()


def test_migration_failure_is_reported(tmp_path, monkeypatch):
    db_path = tmp_path / "cbpos.db"
    db_path.write_bytes(b"this is not a sqlite database" * 100)
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", f"sqlite:///{db_path}")

    assert main.run_migrations()


def test_migrate_only_exits_nonzero_on_failure(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cbpos", "--migrate-only"])
    monkeypatch.setattr(main, "ensure_data_dir", lambda: None)
    monkeypatch.setattr(main, "run_migrations", lambda: "boom")
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)

    def _no_gui(*_args):
        raise AssertionError("--migrate-only must exit before creating the GUI")

    monkeypatch.setattr(main, "QApplication", _no_gui)

    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1


# --- Startup splash steps (#722): name only the migration work that runs ---


def test_status_says_updating_only_when_a_migration_is_applied(old_db):
    seen: list[str] = []
    assert main.run_migrations(status=seen.append) is None
    assert seen == ["startup.checking_data", "startup.updating_data"]

    # Now at head: checked again, nothing to apply, no "updating" line.
    seen.clear()
    assert main.run_migrations(status=seen.append) is None
    assert seen == ["startup.checking_data"]


def test_no_status_when_there_is_no_database_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    seen: list[str] = []
    assert main.run_migrations(status=seen.append) is None
    assert seen == []
