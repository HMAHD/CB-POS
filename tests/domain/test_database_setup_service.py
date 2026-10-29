"""Tests for first-run database setup safety (#833, #791).

Ensures that DatabaseSetupService:
1. Never treats DB errors, missing columns, or locked DBs as "needs setup".
2. Refuses to load demo data over a populated database.
3. Checks the actual active engine in network mode, not the local SQLite file.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from cbpos.core.database import Database
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.database_setup_service import (
    DatabaseNotEmptyError,
    DatabaseSetupService,
    DatabaseUnavailableError,
    SetupState,
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Provide a throwaway SQLite database and isolate Config.DATA_DIR and Database singleton."""
    db_file = tmp_path / "cbpos.db"
    test_engine = create_engine(f"sqlite:///{db_file}")

    mock_db = MagicMock(spec=Database)
    mock_db.engine = test_engine

    # Isolate Database singleton and Config.DATA_DIR
    monkeypatch.setattr("cbpos.core.services.database_setup_service.Database", lambda: mock_db)
    monkeypatch.setattr("cbpos.core.database.Database", lambda: mock_db)
    monkeypatch.setattr("cbpos.config.Config.DATA_DIR", tmp_path)
    monkeypatch.setattr("cbpos.config.Config.DB_URI", f"sqlite:///{db_file}")

    return db_file, test_engine, mock_db


def test_issue_833_populated_db_with_missing_column_is_not_setup(isolated_db):
    _, engine, _ = isolated_db
    # Create users table missing the locked_until column that ORM User expects
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, pin_hash TEXT)"))
        conn.execute(text("INSERT INTO users (id, username, pin_hash) VALUES (1, 'admin', 'hash')"))

    # check_setup_state() must return READY because users exist, despite missing ORM column
    state = DatabaseSetupService.check_setup_state()
    assert state == SetupState.READY
    # needs_setup() wrapper must be False
    assert DatabaseSetupService.needs_setup() is False


def test_issue_833_query_error_raises_not_setup(isolated_db):
    _, engine, _ = isolated_db
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)"))

    # Simulate locked database / operational error during count
    def _failing_connect(*args, **kwargs):
        raise OperationalError("database is locked", {}, Exception("locked"))

    with patch.object(engine, "connect", side_effect=_failing_connect):
        with pytest.raises(DatabaseUnavailableError):
            DatabaseSetupService.check_setup_state()


def test_issue_833_demo_load_refuses_populated_db(isolated_db):
    _, engine, _ = isolated_db
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO customers (id, name) VALUES (1, 'REAL SHOP CUSTOMER')"))

    with pytest.raises(DatabaseNotEmptyError):
        DatabaseSetupService.create_demo_database()

    # Verify real customer data was NOT wiped by drop_all
    with engine.connect() as conn:
        customer = conn.execute(text("SELECT name FROM customers WHERE id = 1")).scalar()
        assert customer == "REAL SHOP CUSTOMER"


def test_issue_833_network_mode_does_not_use_local_file(tmp_path, monkeypatch):
    # In network mode, local cbpos.db does NOT exist
    local_db_file = tmp_path / "cbpos.db"
    assert not local_db_file.exists()

    remote_engine = create_engine(f"sqlite:///{tmp_path / 'remote.db'}")
    with remote_engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("INSERT INTO users (id, username) VALUES (1, 'admin')"))

    mock_db = MagicMock(spec=Database)
    mock_db.engine = remote_engine

    monkeypatch.setattr("cbpos.core.services.database_setup_service.Database", lambda: mock_db)
    monkeypatch.setattr("cbpos.config.Config.DATA_DIR", tmp_path)
    monkeypatch.setattr(ConfigService, "get", lambda key, *_: "network" if key == "db_mode" else None)

    state = DatabaseSetupService.check_setup_state()
    assert state == SetupState.READY
    assert DatabaseSetupService.needs_setup() is False


def test_issue_833_empty_file_and_missing_file_need_setup(tmp_path, monkeypatch):
    # Case 1: Missing file
    missing_file = tmp_path / "nonexistent.db"
    engine_missing = create_engine(f"sqlite:///{missing_file}")
    mock_db_missing = MagicMock(spec=Database)
    mock_db_missing.engine = engine_missing

    monkeypatch.setattr("cbpos.core.services.database_setup_service.Database", lambda: mock_db_missing)
    monkeypatch.setattr("cbpos.config.Config.DATA_DIR", tmp_path)
    monkeypatch.setattr(ConfigService, "get", lambda key, *_: "standalone")

    assert DatabaseSetupService.check_setup_state() == SetupState.NEEDS_SETUP
    assert DatabaseSetupService.needs_setup() is True

    # Case 2: 0-byte file
    empty_file = tmp_path / "empty.db"
    empty_file.touch()
    assert empty_file.stat().st_size == 0
    engine_empty = create_engine(f"sqlite:///{empty_file}")
    mock_db_empty = MagicMock(spec=Database)
    mock_db_empty.engine = engine_empty
    monkeypatch.setattr("cbpos.core.services.database_setup_service.Database", lambda: mock_db_empty)

    assert DatabaseSetupService.check_setup_state() == SetupState.NEEDS_SETUP
    assert DatabaseSetupService.needs_setup() is True
