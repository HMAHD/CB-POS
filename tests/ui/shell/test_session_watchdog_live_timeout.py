"""#641: the idle-lock timeout was read once, when MainWindow built the
SessionWatchdog -- changing "Lock screen when idle" in Settings did nothing
until the app restarted. SessionWatchdog.set_timeout() applies a new value
to the running session; MainWindow calls it after Settings are saved.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.session_watchdog import SessionWatchdog
from cbpos.ui.main_window import MainWindow
from cbpos.ui.views.settings_pages import SystemPage

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def watchdog(qapp):
    w = SessionWatchdog(timeout_minutes=5)
    yield w
    w.stop_monitoring()
    w.deleteLater()


class TestSetTimeoutDuringASession:
    def test_new_timeout_restarts_the_countdown_with_the_new_length(self, watchdog):
        watchdog.start_monitoring()

        watchdog.set_timeout(2)

        assert watchdog.timer.isActive()
        assert watchdog.timer.interval() == 2 * 60 * 1000

    def test_zero_turns_the_idle_lock_off(self, watchdog):
        watchdog.start_monitoring()

        watchdog.set_timeout(0)

        assert not watchdog.timer.isActive()

    def test_turning_it_on_mid_session_starts_monitoring(self, qapp):
        w = SessionWatchdog(timeout_minutes=0)
        w.start_monitoring()  # logged in while the idle lock was off: a no-op

        w.set_timeout(3)

        assert w.timer.isActive()
        assert w.timer.interval() == 3 * 60 * 1000
        w.stop_monitoring()
        w.deleteLater()


class TestSetTimeoutWhileLoggedOut:
    def test_does_not_start_the_countdown_on_the_login_screen(self, watchdog):
        watchdog.start_monitoring()
        watchdog.stop_monitoring()  # logout

        watchdog.set_timeout(3)

        assert not watchdog.timer.isActive()

    def test_next_login_uses_the_new_timeout(self, watchdog):
        watchdog.set_timeout(7)

        watchdog.start_monitoring()

        assert watchdog.timer.interval() == 7 * 60 * 1000


class TestMainWindowAppliesSavedTimeout:
    """Calls MainWindow._apply_session_timeout() unbound on a plain QWidget,
    so no full MainWindow (and none of its views/timers) is built."""

    def test_reads_the_saved_minutes_into_the_watchdog(self, qapp, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key: {"session_timeout_minutes": 4}.get(key)))
        host = QWidget()
        host.watchdog = MagicMock()

        MainWindow._apply_session_timeout(host)

        host.watchdog.set_timeout.assert_called_once_with(4)
        host.deleteLater()

    def test_missing_or_negative_value_means_off(self, qapp, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key: {"session_timeout_minutes": -3}.get(key)))
        host = QWidget()
        host.watchdog = MagicMock()

        MainWindow._apply_session_timeout(host)

        host.watchdog.set_timeout.assert_called_once_with(0)
        host.deleteLater()


class _FakeConfigStore:
    """In-memory ConfigService, so saving never touches the real settings.json."""

    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data, **_kwargs):
        self._data.update(data)


class TestSavingSettingsUpdatesTheRunningSession:
    @pytest.fixture
    def window(self, qapp, db_session, monkeypatch):
        store = _FakeConfigStore({**ConfigService.DEFAULTS, "session_timeout_minutes": 10})
        for name in ("get", "get_all", "set", "update_all"):
            monkeypatch.setattr(ConfigService, name, getattr(store, name))
        monkeypatch.setattr(
            "cbpos.core.utils.permission_helper.check_permission_with_override", lambda perm, parent: True
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        w = MainWindow()
        yield w
        w.watchdog.stop_monitoring()
        w.deleteLater()
        QApplication.processEvents()

    def test_new_idle_timeout_applies_on_save_without_restart(self, window):
        window.watchdog.start_monitoring()  # a user is logged in
        window.settings_view.load_settings()
        system = next(p for p in window.settings_view.pages if isinstance(p, SystemPage))
        system.chk_timeout.setChecked(True)
        system.spin_timeout.setValue(2)

        window.settings_view.save_all()

        assert window.watchdog.timer.isActive()
        assert window.watchdog.timer.interval() == 2 * 60 * 1000


class TestAbortedTimeoutLogoutResumesWatchdog:
    def test_aborted_timeout_logout_resumes_watchdog_monitoring(self, qapp, db_session, monkeypatch):
        """P1: When a timeout logout is aborted because cart preservation fails,
        the user remains authenticated, watchdog monitoring and its timer restart,
        another inactivity timeout can occur, and no repeated immediate timeout loop occurs.
        """
        from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
        from cbpos.core.models import Role, User
        from cbpos.core.services.auth_service import AuthService

        role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
        if not role:
            role = Role(name=ADMIN_ROLE_NAME)
            db_session.add(role)
            db_session.commit()
        user = User(username="timeout_guard_user", pin_hash="hash", role_id=role.id, is_active=True)
        db_session.add(user)
        db_session.commit()

        store = _FakeConfigStore({**ConfigService.DEFAULTS, "session_timeout_minutes": 5})
        for name in ("get", "get_all", "set", "update_all"):
            monkeypatch.setattr(ConfigService, name, getattr(store, name))

        w = MainWindow()
        try:
            # Log in
            AuthService._current_user = user
            w.user = user
            w.watchdog.set_timeout(5)
            w.watchdog.start_monitoring()

            assert w.watchdog._monitoring is True
            assert w.watchdog.timer.isActive() is True

            # Patch sales_view.end_session to fail cart preservation
            monkeypatch.setattr(w.sales_view, "end_session", lambda reason=None: False)

            # Trigger timeout
            w.watchdog.on_timeout()

            # 1. User remains authenticated
            assert AuthService.get_current_user() is not None
            assert AuthService.get_current_user().id == user.id
            assert w.user is not None

            # 2. Watchdog monitoring and its timer restart
            assert w.watchdog._monitoring is True, "Watchdog monitoring must resume when timeout logout is aborted"
            assert w.watchdog.timer.isActive() is True, (
                "Watchdog timer must be active to allow future timeout protection"
            )
            assert w.watchdog.timer.interval() == 5 * 60 * 1000

            # 3. Prove another inactivity timeout can occur
            # When cart preservation succeeds later, logout succeeds
            monkeypatch.setattr(w.sales_view, "end_session", lambda reason=None: True)
            w.watchdog.on_timeout()
            assert AuthService.get_current_user() is None
            assert w.user is None
            assert w.watchdog._monitoring is False
        finally:
            w.watchdog.stop_monitoring()
            w.deleteLater()
            QApplication.processEvents()
            AuthService._current_user = None
