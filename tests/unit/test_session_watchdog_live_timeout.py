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
