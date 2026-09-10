"""
Two separate reliability bugs in the same feature:

Bug 1 -- main.py only created the scheduler QTimer if auto_report_enabled
was already True at process launch. Nothing in settings_view.py or
main_window.py started or stopped it when the setting changed mid-session,
so toggling the checkbox and saving had no effect until a full restart.

Bug 2 -- EmailService.send_email_with_pdf fired the real send on a
detached background thread with no completion callback wired up, and
scheduler_service.py logged "Auto-Report sent" and marked
auto_report_last_run immediately, before the thread had actually
attempted delivery -- so a genuine SMTP failure was invisible, and the
day was marked "done" regardless of whether the email ever went out.
"""

from unittest.mock import MagicMock

import pytest

from cbpos.core.services.scheduler_service import SchedulerService

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    """In-memory stand-in for ConfigService so these tests never touch
    the real, developer-shared settings.json on disk."""

    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture(autouse=True)
def _reset_scheduler_timer():
    """SchedulerService owns one process-wide QTimer -- make sure a timer
    started by one test doesn't leak into the next."""
    yield
    SchedulerService.stop_timer()
    SchedulerService._timer = None
    SchedulerService._pending_email_result = None


@pytest.fixture
def config_store(monkeypatch):
    import cbpos.core.services.scheduler_service as scheduler_service_module

    store = _FakeConfigStore({"auto_report_enabled": False})
    monkeypatch.setattr(scheduler_service_module.ConfigService, "get", store.get)
    monkeypatch.setattr(scheduler_service_module.ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(scheduler_service_module.ConfigService, "set", store.set)
    return store


class TestSchedulerTimerLiveToggle:
    def test_start_timer_actually_starts_it(self, config_store):
        assert SchedulerService.is_timer_running() is False
        SchedulerService.start_timer()
        assert SchedulerService.is_timer_running() is True

    def test_stop_timer_actually_stops_it(self, config_store):
        SchedulerService.start_timer()
        SchedulerService.stop_timer()
        assert SchedulerService.is_timer_running() is False

    def test_starting_twice_does_not_create_a_second_timer(self, config_store):
        SchedulerService.start_timer()
        first_timer = SchedulerService._timer
        SchedulerService.start_timer()
        assert SchedulerService._timer is first_timer


class TestEmailResultOnlyPersistedOnConfirmedOutcome:
    def test_successful_send_marks_last_run_and_clears_last_error(self, config_store):
        SchedulerService._pending_email_result = (True, "Email sent successfully.", "2026-01-15")

        SchedulerService.check_automation()

        assert config_store.get("auto_report_last_run") == "2026-01-15"
        assert config_store.get("auto_report_last_error") == ""

    def test_failed_send_records_the_error_but_does_not_mark_last_run(self, config_store):
        SchedulerService._pending_email_result = (False, "SMTP auth failed", "2026-01-15")

        SchedulerService.check_automation()

        assert config_store.get("auto_report_last_run") is None
        assert config_store.get("auto_report_last_error") == "SMTP auth failed"

    def test_pending_result_is_cleared_after_being_flushed(self, config_store):
        SchedulerService._pending_email_result = (True, "ok", "2026-01-15")

        SchedulerService.check_automation()

        assert SchedulerService._pending_email_result is None


class TestProcessAutoReportWiresUpTheCallback:
    def test_send_email_with_pdf_is_called_with_a_callback(self, config_store, monkeypatch):
        import cbpos.core.services.scheduler_service as scheduler_service_module

        config_store.set("auto_report_enabled", True)
        config_store.set("auto_report_time", "00:00")
        config_store.set("admin_email", "owner@example.com")
        config_store.set("auto_report_last_run", "")

        fake_df = MagicMock()
        fake_df.empty = False
        monkeypatch.setattr(scheduler_service_module.DailySalesSummaryReport, "generate", lambda self, filters: fake_df)
        monkeypatch.setattr(scheduler_service_module.ExportService, "export_to_pdf", lambda self, *a, **k: None)

        send_mock = MagicMock()
        monkeypatch.setattr(scheduler_service_module.EmailService, "send_email_with_pdf", send_mock)

        SchedulerService.check_automation()

        send_mock.assert_called_once()
        assert "callback" in send_mock.call_args.kwargs
        assert callable(send_mock.call_args.kwargs["callback"])

        # auto_report_last_run must NOT be set yet -- only the callback,
        # once it actually fires with a real outcome, may set it.
        assert config_store.get("auto_report_last_run") == ""
