"""
save_all() previously wrote auto_report_enabled to ConfigService with no
code anywhere starting or stopping the scheduler QTimer to match -- the
setting only took effect on the next full app restart. save_all() must
now start/stop SchedulerService's timer live when this checkbox's saved
value actually changes.
"""

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.ui.views.settings_view import SettingsView

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    """In-memory stand-in for ConfigService so these tests never touch
    the real, developer-shared settings.json on disk -- a prior version
    of this test file didn't mock ConfigService at all and ended up
    permanently flipping auto_report_enabled to True in the real file,
    which then made every subsequent run see "no change" and silently
    fail to exercise the code under test at all."""

    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        # Real ConfigService.get() takes only `key` -- no `default` param.
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data, **_kwargs):
        self._data.update(data)


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore({"auto_report_enabled": False, "language": "en", "theme": "Dark", "font_size": 12})

    # ConfigService is a shared class object regardless of which module
    # imported it, so patching it once here covers every caller.
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(ConfigService, "set", store.set)
    monkeypatch.setattr(ConfigService, "update_all", store.update_all)
    return store


@pytest.fixture
def view(qapp, db_session, config_store, monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent: True,
    )
    # save_all() ends with a real QMessageBox.information() -- confirmed
    # (via an isolated probe) to block indefinitely under this offscreen
    # platform rather than auto-returning, so it must be mocked here.
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    v = SettingsView()
    yield v
    v.deleteLater()


class TestSchedulerTimerStartsAndStopsWithTheSetting:
    def test_enabling_auto_report_starts_the_scheduler_timer(self, view, config_store, monkeypatch):
        from cbpos.core.services.scheduler_service import SchedulerService

        monkeypatch.setattr(SchedulerService, "start_timer", lambda: setattr(view, "_started", True))
        monkeypatch.setattr(SchedulerService, "stop_timer", lambda: setattr(view, "_stopped", True))
        view._started = False
        view._stopped = False

        for page in view.pages:
            if hasattr(page, "chk_auto_report"):
                page.chk_auto_report.setChecked(True)

        view.save_all()

        assert view._started is True
        assert view._stopped is False

    def test_disabling_auto_report_stops_the_scheduler_timer(self, view, config_store, monkeypatch):
        from cbpos.core.services.scheduler_service import SchedulerService

        config_store.set("auto_report_enabled", True)
        view.load_settings()

        monkeypatch.setattr(SchedulerService, "start_timer", lambda: setattr(view, "_started", True))
        monkeypatch.setattr(SchedulerService, "stop_timer", lambda: setattr(view, "_stopped", True))
        view._started = False
        view._stopped = False

        for page in view.pages:
            if hasattr(page, "chk_auto_report"):
                page.chk_auto_report.setChecked(False)

        view.save_all()

        assert view._stopped is True
        assert view._started is False

    def test_saving_with_no_change_touches_neither_start_nor_stop(self, view, config_store, monkeypatch):
        from cbpos.core.services.scheduler_service import SchedulerService

        monkeypatch.setattr(SchedulerService, "start_timer", lambda: setattr(view, "_started", True))
        monkeypatch.setattr(SchedulerService, "stop_timer", lambda: setattr(view, "_stopped", True))
        view._started = False
        view._stopped = False

        view.save_all()

        assert view._started is False
        assert view._stopped is False
