import pytest
import sys
import os

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from cbpos.config import Config  # noqa: E402
from cbpos.core.database import Base, Database  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# Force in-memory DB for tests
# We import Config from cbpos.core.database to ensure we patch the exact object used there
from cbpos.core.database import Config as DBConfig  # noqa: E402

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

    # Nested transaction (savepoint) for extra safety if needed,
    # but connection-level transaction is usually enough for rollback.
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.expire_all()
            session.begin_nested()

    yield session

    # Cleanup
    # Restore close so we can actually close it
    session.close = original_close
    session.close()
    transaction.rollback()
    connection.close()

    # Restore original factory
    db.SessionLocal = original_factory
