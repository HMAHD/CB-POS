"""Tests for scheduler auto-report worker, backoff, and owner notice (#882)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication, QMessageBox

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.scheduler_service import AutoReportWorker, SchedulerService
from cbpos.ui.views.management_view import ManagementView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def clean_config():
    """Reset scheduler config keys before and after each test."""
    keys = [
        "auto_report_enabled",
        "auto_report_time",
        "auto_report_last_sent_date",
        "auto_report_last_run",
        "auto_report_in_progress_since",
        "auto_report_failures",
        "auto_report_failures_date",
        "auto_report_next_attempt",
        "auto_report_pending_notice",
        "auto_report_last_error",
        "admin_email",
    ]
    for k in keys:
        if k == "auto_report_failures":
            ConfigService.set(k, 0)
        elif k == "auto_report_enabled":
            ConfigService.set(k, False)
        else:
            ConfigService.set(k, "")
    SchedulerService._email_sender = None
    yield
    for k in keys:
        if k == "auto_report_failures":
            ConfigService.set(k, 0)
        elif k == "auto_report_enabled":
            ConfigService.set(k, False)
        else:
            ConfigService.set(k, "")
    SchedulerService._email_sender = None


def test_issue_882_slow_send_sends_once(qapp, monkeypatch):
    """When a send is currently in progress (<15m), subsequent ticks do not start another send."""
    now = datetime(2026, 10, 15, 22, 5)
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.datetime",
        MagicMock(now=lambda: now, strptime=datetime.strptime, fromisoformat=datetime.fromisoformat),
    )

    ConfigService.set("auto_report_enabled", True)
    ConfigService.set("auto_report_time", "22:00")
    ConfigService.set("admin_email", "owner@example.com")
    ConfigService.set("auto_report_in_progress_since", (now - timedelta(minutes=2)).isoformat())

    started_workers = []
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.start_background_job",
        lambda w: started_workers.append(w),
    )

    SchedulerService.check_automation()

    assert len(started_workers) == 0


def test_issue_882_stuck_in_progress_clears_after_15_minutes(qapp, monkeypatch):
    """When in_progress_since is older than 15 minutes, it is treated as stuck, cleared, and retried."""
    now = datetime(2026, 10, 15, 22, 20)
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.datetime",
        MagicMock(now=lambda: now, strptime=datetime.strptime, fromisoformat=datetime.fromisoformat),
    )

    ConfigService.set("auto_report_enabled", True)
    ConfigService.set("auto_report_time", "22:00")
    ConfigService.set("admin_email", "owner@example.com")
    ConfigService.set("auto_report_in_progress_since", (now - timedelta(minutes=16)).isoformat())

    started_workers = []
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.start_background_job",
        lambda w: started_workers.append(w),
    )

    SchedulerService.check_automation()

    assert len(started_workers) == 1
    assert ConfigService.get("auto_report_in_progress_since") == now.isoformat()


def test_issue_882_failing_send_backs_off(qapp, monkeypatch):
    """Failure triggers exponential backoff (min(2^failures * 5m, 6h)), skipping ticks while now < next_attempt."""
    now = datetime(2026, 10, 15, 22, 0)
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.datetime",
        MagicMock(now=lambda: now, strptime=datetime.strptime, fromisoformat=datetime.fromisoformat),
    )

    ConfigService.set("auto_report_enabled", True)
    ConfigService.set("auto_report_time", "22:00")
    ConfigService.set("admin_email", "owner@example.com")

    # Simulate worker failure 1: 2^1 * 300s = 600s (10 min)
    SchedulerService._on_worker_failure("SMTP authentication failed")

    assert ConfigService.get("auto_report_failures") == 1
    assert ConfigService.get("auto_report_failures_date") == "2026-10-15"
    expected_next = (now + timedelta(seconds=600)).isoformat()
    assert ConfigService.get("auto_report_next_attempt") == expected_next

    # Next tick 5 minutes later (< 10 min backoff) should be skipped
    now_5m = now + timedelta(minutes=5)
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.datetime",
        MagicMock(now=lambda: now_5m, strptime=datetime.strptime, fromisoformat=datetime.fromisoformat),
    )

    started_workers = []
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.start_background_job",
        lambda w: started_workers.append(w),
    )
    SchedulerService.check_automation()
    assert len(started_workers) == 0

    # Simulate failure 2: 2^2 * 300s = 1200s (20 min)
    SchedulerService._on_worker_failure("Connection timed out")
    assert ConfigService.get("auto_report_failures") == 2
    assert ConfigService.get("auto_report_next_attempt") == (now_5m + timedelta(seconds=1200)).isoformat()


def test_issue_882_max_failures_stops_and_sets_pending_notice(qapp, monkeypatch):
    """After 5 failures in a day, stops retries for that day and sets auto_report_pending_notice."""
    now = datetime(2026, 10, 15, 22, 0)
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.datetime",
        MagicMock(now=lambda: now, strptime=datetime.strptime, fromisoformat=datetime.fromisoformat),
    )

    ConfigService.set("auto_report_enabled", True)
    ConfigService.set("auto_report_time", "22:00")
    ConfigService.set("admin_email", "owner@example.com")
    ConfigService.set("auto_report_failures", 4)
    ConfigService.set("auto_report_failures_date", "2026-10-15")

    # 5th failure
    SchedulerService._on_worker_failure("SMTP connection refused: password=supersecret")

    assert ConfigService.get("auto_report_failures") == 5
    notice = ConfigService.get("auto_report_pending_notice")
    assert "supersecret" not in notice
    assert "SMTP connection refused" in notice

    # Subsequent check should do nothing because max failures reached
    started_workers = []
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.start_background_job",
        lambda w: started_workers.append(w),
    )
    SchedulerService.check_automation()
    assert len(started_workers) == 0


def test_issue_882_build_runs_off_ui_thread(qapp):
    """DailySalesSummaryReport.generate and ExportService.export_to_pdf run on worker thread, off UI thread."""
    had_inline_start = "start" in AutoReportWorker.__dict__
    if had_inline_start:
        del AutoReportWorker.start

    try:
        main_thread = QThread.currentThread()
        worker_threads = {}

        class FakeReport:
            def generate(self, filters):
                worker_threads["generate"] = QThread.currentThread()
                df = MagicMock()
                df.empty = False
                return df

        class FakeExport:
            def export_to_pdf(self, df, path, title):
                worker_threads["export"] = QThread.currentThread()

        def fake_sender(email, subj, body, path):
            worker_threads["sender"] = QThread.currentThread()

        SchedulerService._email_sender = fake_sender

        with (
            patch("cbpos.core.services.scheduler_service.DailySalesSummaryReport", FakeReport),
            patch("cbpos.core.services.scheduler_service.ExportService", FakeExport),
        ):
            worker = AutoReportWorker(
                today_str="2026-10-15",
                admin_email="owner@example.com",
                receipt_lang="en",
            )
            worker.start()
            assert worker.wait(5000) is True

            assert worker_threads["generate"] != main_thread
            assert worker_threads["export"] != main_thread
            assert worker_threads["sender"] != main_thread
            assert worker_threads["generate"] == worker_threads["export"] == worker_threads["sender"]
    finally:
        if had_inline_start:
            AutoReportWorker.start = AutoReportWorker.run


def test_issue_882_empty_report_does_not_set_last_sent_date():
    """Empty report marks last_run so it doesn't repeat, but does NOT set last_sent_date."""
    SchedulerService._on_worker_success("2026-10-15", is_empty=True)
    assert ConfigService.get("auto_report_last_run") == "2026-10-15"
    assert ConfigService.get("auto_report_last_sent_date") == ""


def test_issue_882_non_numeric_failures_handled_gracefully():
    """Corrupted/non-numeric auto_report_failures in config does not crash tick or failure handler."""
    ConfigService.set("auto_report_failures", "corrupted_string")
    SchedulerService._on_worker_failure("Error message")
    assert ConfigService.get("auto_report_failures") == 1


def test_issue_882_owner_notice_displayed_and_cleared_for_eligible_user(qapp, monkeypatch):
    """ManagementView shows notice for user with ADMIN_SETTINGS, navigates to Email settings, and clears notice."""
    ConfigService.set("auto_report_pending_notice", "SMTP server offline")

    eligible_user = User(id=1, username="admin", pin_hash="hash")
    ineligible_user = User(id=2, username="cashier", pin_hash="hash")

    monkeypatch.setattr(
        "cbpos.core.services.permission_service.PermissionService.user_has_permission",
        lambda u, perm: perm == Permissions.ADMIN_SETTINGS if u == eligible_user else False,
    )

    view = ManagementView()

    # For ineligible user: notice is NOT shown and NOT cleared
    view.set_user(ineligible_user)
    view._check_auto_report_notice()
    assert ConfigService.get("auto_report_pending_notice") == "SMTP server offline"

    # For eligible user: box shown, cleared from config, and clicking Open Email settings navigates
    view.set_user(eligible_user)

    emitted_nav = []
    view.open_settings_requested.connect(lambda page, tab: emitted_nav.append((page, tab)))

    # Mock QMessageBox.exec and clickedButton to simulate clicking 'Open Email settings'
    def fake_exec(self_box):
        # find the accept button
        for btn in self_box.buttons():
            if self_box.buttonRole(btn) == QMessageBox.ButtonRole.AcceptRole:
                self_box._mock_clicked = btn
                return 1
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self_box: getattr(self_box, "_mock_clicked", None))

    view._check_auto_report_notice()

    assert ConfigService.get("auto_report_pending_notice") == ""
    from cbpos.ui.views.settings_pages.shop_info import ShopInfoPage
    from cbpos.ui.views.settings_view import SettingsView

    assert emitted_nav == [(SettingsView.SHOP_INFO_PAGE, ShopInfoPage.TAB_EMAIL)]
