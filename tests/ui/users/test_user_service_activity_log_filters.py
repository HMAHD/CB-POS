"""
#302: get_recent_activity() was hardcoded to the 10 most recent audit log
rows system-wide, with no way to narrow by event type or date range --
so the Activity Log tab could never show anything older than whatever
happened to fall in the last 10 events across every user and terminal.
"""

from datetime import datetime, timedelta

import pytest

from cbpos.core.models import AuditLog, Permission, Role, User
from cbpos.core.services.user_service import UserService

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_user(db_session):
    suffix = _next_suffix()
    permission = Permission(code=f"activity_log_test_{suffix}")
    role = Role(name=f"ActivityLogRole_{suffix}", permissions=[permission])
    user = User(username=f"activity_log_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


def _log(db_session, user, event_type, action, timestamp=None):
    log = AuditLog(
        user_id=user.id,
        action=action,
        event_type=event_type,
        timestamp=timestamp or datetime.now(),
    )
    db_session.add(log)
    db_session.flush()
    return log


class TestDefaultLimit:
    def test_default_limit_returns_far_more_than_ten_rows(self, db_session, test_user):
        for _ in range(50):
            _log(db_session, test_user, "LOGIN", "LOGIN")

        logs = UserService.get_recent_activity()

        assert len(logs) == 50


class TestEventTypeFilter:
    def test_filters_to_only_the_requested_event_type(self, db_session, test_user):
        _log(db_session, test_user, "LOGIN", "LOGIN")
        _log(db_session, test_user, "SECURITY", "TAX_RATE_CHANGE")
        _log(db_session, test_user, "SECURITY", "PROFILE_UPDATE")

        logs = UserService.get_recent_activity(event_type="SECURITY")

        assert len(logs) == 2
        assert all(log.event_type == "SECURITY" for log in logs)


class TestDateRangeFilter:
    def test_filters_out_entries_before_date_from(self, db_session, test_user):
        _log(db_session, test_user, "LOGIN", "LOGIN", timestamp=datetime.now() - timedelta(days=10))
        recent = _log(db_session, test_user, "LOGIN", "LOGIN", timestamp=datetime.now())

        logs = UserService.get_recent_activity(date_from=datetime.now() - timedelta(days=1))

        assert [log.id for log in logs] == [recent.id]

    def test_filters_out_entries_after_date_to(self, db_session, test_user):
        old = _log(db_session, test_user, "LOGIN", "LOGIN", timestamp=datetime.now() - timedelta(days=10))
        _log(db_session, test_user, "LOGIN", "LOGIN", timestamp=datetime.now())

        logs = UserService.get_recent_activity(date_to=datetime.now() - timedelta(days=1))

        assert [log.id for log in logs] == [old.id]


class TestTerminalFilter:
    def test_filters_by_terminal_id_and_returns_distinct_terminals(self, db_session, test_user):
        log1 = AuditLog(
            user_id=test_user.id,
            action="LOGIN",
            event_type="LOGIN",
            terminal_id="TERM-01",
            timestamp=datetime.now(),
        )
        log2 = AuditLog(
            user_id=test_user.id,
            action="LOGIN",
            event_type="LOGIN",
            terminal_id="TERM-02",
            timestamp=datetime.now(),
        )
        db_session.add_all([log1, log2])
        db_session.flush()

        terminals = UserService.get_distinct_terminals()
        assert "TERM-01" in terminals
        assert "TERM-02" in terminals

        logs = UserService.get_recent_activity(terminal_id="TERM-02")
        assert len(logs) == 1
        assert logs[0].terminal_id == "TERM-02"
