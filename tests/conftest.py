import os
import sys

import pytest

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from sqlalchemy import event
from sqlalchemy.orm import Session

from cbpos.config import Config
from cbpos.core.database import Base, Database

# Force in-memory DB for tests
# We import Config from cbpos.core.database to ensure we patch the exact object
# used there
from cbpos.core.database import Config as DBConfig

DBConfig.DB_URI = "sqlite:///:memory:"
Config.DB_URI = "sqlite:///:memory:"  # Patch global config too just in case


@pytest.fixture(scope="session")
def app_fixture(qapp):
    """
    Fixture to manage QApplication instance.
    pytest-qt provides 'qapp' fixture.
    """
    return qapp


@pytest.fixture(scope="session")
def test_engine():
    """
    Create a single engine for the test session.
    """
    # Reset Database singleton to ensure it uses our config
    Database._instance = None
    db = Database()

    # Create tables
    Base.metadata.create_all(bind=db.engine)

    return db.engine


@pytest.fixture
def db_session(test_engine):
    """
    Transactional fixture that rolls back after each test.
    Patches Database.SessionLocal to return this session.

    Uses SQLAlchemy 2.0's documented "join a Session into an external
    transaction" recipe: the SAVEPOINT is tracked as a Core-level
    ``connection.begin_nested()`` handle, not a ``session.begin_nested()``
    one. The previous version tracked it at the ORM/session level, which
    let a service's ``session.commit()`` (e.g. any read-only
    ``get_session()`` call) collapse the SAVEPOINT into the connection's
    real outer transaction -- so anything written earlier in the same
    test via a bare ``db_session.add(...); db_session.flush()`` (no
    commit) silently survived this fixture's rollback and leaked into
    every later test sharing the same in-memory database.
    """
    connection = test_engine.connect()
    transaction = connection.begin()

    # Bind session to the connection
    session = Session(bind=connection)

    # Patch Database.SessionLocal to return our test session
    # Services call db.SessionLocal(), so we mock it to return our session
    db = Database()
    original_factory = db.SessionLocal

    # We mock the factory to return our existing session
    # We also need to prevent session.close() from actually closing the connection
    # inside the service, as we want to control the transaction here.
    # We can mock close() on the session object itself.
    original_close = session.close
    session.close = lambda: None

    db.SessionLocal = lambda: session

    # Core-level SAVEPOINT, restarted whenever it ends (e.g. a service's
    # own session.commit()/rollback() releases it) so writes always stay
    # nested inside `transaction`, the one this fixture actually rolls
    # back at teardown.
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, _transaction):
        nonlocal nested
        if not nested.is_active:
            session.expire_all()
            nested = connection.begin_nested()

    yield session

    # Cleanup
    # Restore close so we can actually close it
    session.close = original_close
    session.close()
    transaction.rollback()
    connection.close()

    # Restore original factory
    db.SessionLocal = original_factory
