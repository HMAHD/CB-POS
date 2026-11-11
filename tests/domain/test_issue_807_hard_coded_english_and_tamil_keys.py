"""Tests for Issue #807: Hard-coded English (crash dialog, daily email) and missing Tamil keys."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from cbpos.core.services.scheduler_service import SchedulerService
from main import _report_crash


class TestCrashDialogI18n:
    def test_crash_dialog_uses_i18n_translation(self, monkeypatch):
        """Crash dialog must use _t('crash.title') and _t('crash.body', path=...)."""
        from PyQt6.QtWidgets import QApplication, QMessageBox

        # Ensure a QApplication exists
        _ = QApplication.instance() or QApplication([])

        mock_critical = MagicMock()
        monkeypatch.setattr(QMessageBox, "critical", mock_critical)
        monkeypatch.setattr("main._close_splash", lambda: None)

        try:
            raise ValueError("Test unexpected crash")
        except ValueError as err:
            _report_crash(type(err), err, err.__traceback__)

        mock_critical.assert_called_once()
        _, title, message = mock_critical.call_args[0]
        assert title == "CB POS"
        assert "logs" in message
        assert "CB POS ran into a problem and needs to close." in message

    def test_crash_dialog_fails_safe_when_i18n_fails(self, monkeypatch):
        """When i18n cannot be imported or raises, crash dialog falls back to English literal without crashing."""
        from PyQt6.QtWidgets import QApplication, QMessageBox

        _ = QApplication.instance() or QApplication([])

        mock_critical = MagicMock()
        monkeypatch.setattr(QMessageBox, "critical", mock_critical)
        monkeypatch.setattr("main._close_splash", lambda: None)

        # Force import or _t to fail
        import cbpos.i18n

        monkeypatch.setattr(cbpos.i18n, "_t", MagicMock(side_effect=RuntimeError("i18n not initialized")))

        try:
            raise RuntimeError("Early crash before i18n")
        except RuntimeError as err:
            _report_crash(type(err), err, err.__traceback__)

        mock_critical.assert_called_once()
        _, title, message = mock_critical.call_args[0]
        assert title == "CB POS"
        assert "logs" in message
        assert "CB POS ran into a problem and needs to close." in message


class TestDailyReportEmailI18n:
    @pytest.mark.parametrize(
        "receipt_lang,expected_subj_prefix,expected_title_prefix",
        [
            ("en", "Daily Sales Report", "Daily Sales Summary"),
            ("si", "දෛනික විකුණුම් වාර්තාව", "දෛනික විකුණුම් සාරාංශය"),
            ("ta", "தினசரி விற்பனை அறிக்கை", "தினசரி விற்பனை சுருக்கம்"),
        ],
    )
    def test_daily_email_uses_receipt_language(
        self, monkeypatch, receipt_lang, expected_subj_prefix, expected_title_prefix
    ):
        """Daily email subject, body, and PDF title must follow the configured receipt_language."""
        from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
        from cbpos.core.services.email_service import EmailService
        from cbpos.core.services.export_service import ExportService

        # Mock report generate to return non-empty df
        dummy_df = pd.DataFrame([{"Item": "Tea", "Total": 500}])
        monkeypatch.setattr(DailySalesSummaryReport, "generate", lambda self, filters: dummy_df)

        captured_export = {}

        def mock_export_to_pdf(self, df, filepath, title="Report"):
            captured_export["filepath"] = filepath
            captured_export["title"] = title

        monkeypatch.setattr(ExportService, "export_to_pdf", mock_export_to_pdf)

        captured_email = {}

        def mock_send_email_with_pdf(to_email, subject, body, filepath, callback=None):
            captured_email["to_email"] = to_email
            captured_email["subject"] = subject
            captured_email["body"] = body
            captured_email["filepath"] = filepath

        monkeypatch.setattr(EmailService, "send_email_with_pdf", mock_send_email_with_pdf)

        config = {
            "auto_report_enabled": True,
            "auto_report_time": "00:00",
            "auto_report_last_run": "",
            "admin_email": "admin@example.com",
            "receipt_language": receipt_lang,
        }

        SchedulerService._process_auto_report(config)

        assert expected_subj_prefix in captured_email["subject"]
        assert expected_title_prefix in captured_export["title"]
        assert "ceybyte.com" in captured_email["body"]
        assert "CB POS" in captured_email["body"]
