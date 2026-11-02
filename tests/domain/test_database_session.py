"""Tests for Database.get_session() and session error handling."""

import pytest
from sqlalchemy.exc import OperationalError

from cbpos.core.database import Database
from cbpos.core.utils.error_messages import translate_error


def test_issue_904_operational_error_reaches_caller(monkeypatch):
    """#904: OperationalError in network mode must reach caller directly, not raise RuntimeError."""
    db = Database()
    monkeypatch.setattr(db, "_db_mode", "network")

    call_count = 0

    with pytest.raises(OperationalError) as exc_info:
        with db.get_session():
            call_count += 1
            raise OperationalError("SELECT 1", {}, Exception("Connection terminated"))

    # The body must run exactly once (no retry loop yielding twice)
    assert call_count == 1
    assert "Connection terminated" in str(exc_info.value)


def test_translate_error_operational_error():
    """translate_error maps OperationalError and connection error strings to db_connection_lost."""
    err = OperationalError("SELECT 1", {}, Exception("could not connect to server"))
    msg = translate_error(err)
    assert "Lost connection to the shop database" in msg

    msg_from_str = translate_error("psycopg2.OperationalError: server closed the connection unexpectedly")
    assert "Lost connection to the shop database" in msg_from_str


def test_session_serializable_postgres(monkeypatch):
    """When serializable=True and in network mode, SET TRANSACTION ISOLATION LEVEL is issued."""
    db = Database()
    monkeypatch.setattr(db, "_db_mode", "network")

    executed_sql = []

    class DummySession:
        def execute(self, statement):
            executed_sql.append(str(statement))

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(db, "SessionLocal", lambda: DummySession())

    with db.get_session(serializable=True):
        pass

    assert any("SERIALIZABLE" in sql for sql in executed_sql)
