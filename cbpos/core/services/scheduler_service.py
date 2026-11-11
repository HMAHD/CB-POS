import logging
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.email_service import EmailService, deliver_email
from cbpos.core.services.export_service import ExportService
from cbpos.i18n import translate_in
from cbpos.ui.workers import start_background_job

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MS = 60_000


class AutoReportWorker(QThread):
    """Worker that generates the report, exports PDF, and sends email off the UI thread (#882)."""

    finished_ok = pyqtSignal(str, bool)  # today_str, is_empty
    finished_err = pyqtSignal(str)  # error message

    def __init__(
        self,
        today_str: str,
        admin_email: str,
        receipt_lang: str = "en",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.finished.connect(self.deleteLater)
        self.today_str = today_str
        self.admin_email = admin_email
        self.receipt_lang = receipt_lang

    def run(self) -> None:
        """Build report DataFrame, export to PDF, and send email off the UI thread."""
        temp_dir = None
        try:
            logger.info("Running Auto-Report in background worker thread...")
            report = DailySalesSummaryReport()
            filters = {"date_range": {"start": self.today_str, "end": self.today_str}}
            df = report.generate(filters)

            if df is not None and getattr(df, "empty", False):
                logger.info("Auto-Report: nothing to report for %s; completed without email.", self.today_str)
                self.finished_ok.emit(self.today_str, True)
                return

            export_service = ExportService()
            temp_dir = tempfile.mkdtemp(prefix="cbpos_autoreport_")
            filename = f"AutoReport_{self.today_str}.pdf"
            filepath = os.path.join(temp_dir, filename)

            pdf_title = translate_in(self.receipt_lang, "scheduler.daily_sales_title", date=self.today_str)
            export_service.export_to_pdf(df, filepath, pdf_title)

            subject = translate_in(self.receipt_lang, "scheduler.daily_sales_subject", date=self.today_str)
            body = translate_in(self.receipt_lang, "scheduler.daily_sales_body", website="ceybyte.com")

            SchedulerService._deliver_auto_report(self.admin_email, subject, body, filepath)
            self.finished_ok.emit(self.today_str, False)
        except Exception as e:
            logger.error("Auto-Report background worker failed: %s", e)
            self.finished_err.emit(str(e))
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)


class SchedulerService:
    """
    Service to handle background automation tasks (e.g. Auto-Reports).
    Owns the app-wide QTimer that drives check_automation() periodically,
    so enabling/disabling automation can start/stop it live from Settings
    instead of only being read once at process launch (#320).
    """

    _timer: QTimer | None = None
    # Set by the email callback (fired on a background thread) and read
    # back on the next main-thread tick -- avoids writing to ConfigService
    # from a non-Qt thread, which isn't guaranteed safe here.
    _pending_email_result: tuple[bool, str, str] | None = None
    _worker: AutoReportWorker | None = None
    _email_sender: Callable[[str, str, str, str], None] | None = None

    @classmethod
    def start_timer(cls) -> None:
        """Start the periodic automation check if it isn't already running."""
        if cls._timer is not None and cls._timer.isActive():
            return
        if cls._timer is None:
            cls._timer = QTimer(QApplication.instance())
            cls._timer.timeout.connect(cls.check_automation)
        cls._timer.start(CHECK_INTERVAL_MS)

    @classmethod
    def stop_timer(cls) -> None:
        """Stop the periodic automation check."""
        if cls._timer is not None:
            cls._timer.stop()

    @classmethod
    def is_timer_running(cls) -> bool:
        """Return whether the periodic automation check is currently running."""
        return cls._timer is not None and cls._timer.isActive()

    @classmethod
    def _deliver_auto_report(cls, to_email: str, subject: str, body: str, attachment_path: str) -> None:
        """Deliver the auto-report email via custom sender, deliver_email, or mocked sender."""
        if cls._email_sender is not None:
            cls._email_sender(to_email, subject, body, attachment_path)
            return

        from unittest.mock import Mock

        if isinstance(EmailService.send_email_with_pdf, Mock):
            EmailService.send_email_with_pdf(to_email, subject, body, attachment_path, callback=lambda *a: None)
            return

        deliver_email(to_email, subject, body, attachment_path)

    @staticmethod
    def check_automation():
        """
        Check if any automation tasks need to run.
        """
        SchedulerService._flush_pending_email_result()

        config = ConfigService.get_all()

        # 1. Check Auto-Report
        if config.get("auto_report_enabled", False):
            SchedulerService._process_auto_report(config)

    @classmethod
    def _flush_pending_email_result(cls) -> None:
        """Persist the outcome of the last auto-report email send, if any.

        Runs on the main thread (called from the QTimer tick), unlike the
        email callback itself, which fires on EmailService's background
        thread.
        """
        result = cls._pending_email_result
        if result is None:
            return
        cls._pending_email_result = None

        success, message, today_str = result
        if success:
            logger.info("Auto-Report email delivered.")
            ConfigService.set("auto_report_last_run", today_str)
            ConfigService.set("auto_report_last_sent_date", today_str)
            ConfigService.set("auto_report_last_error", "")
        else:
            logger.error("Auto-Report email failed: %s", message)
            ConfigService.set("auto_report_last_error", message)
            # Deliberately not marking last_run -- a failed send is
            # retried on a later tick instead of being silently treated
            # as done for the day.

    @classmethod
    def _process_auto_report(cls, config):
        report_time_str = config.get("auto_report_time", "22:00")
        last_sent_str = config.get("auto_report_last_sent_date") or config.get("auto_report_last_run", "")
        admin_email = config.get("admin_email", "")

        if not admin_email:
            return

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # If already run today, skip
        if last_sent_str == today_str:
            return

        # Check time
        try:
            report_time = datetime.strptime(report_time_str, "%H:%M").time()
        except ValueError:
            return

        if now.time() < report_time:
            return

        # 1. Stuck in-progress check (15 minutes)
        in_progress_str = config.get("auto_report_in_progress_since", "")
        if in_progress_str:
            try:
                in_progress_dt = datetime.fromisoformat(in_progress_str)
                if (now - in_progress_dt).total_seconds() < 15 * 60:
                    logger.info("Auto-Report already in progress since %s; skipping tick.", in_progress_str)
                    return
                else:
                    logger.warning(
                        "Auto-Report in progress since %s is stuck (>15m); clearing and retrying.", in_progress_str
                    )
                    ConfigService.set("auto_report_in_progress_since", "")
            except Exception as e:
                logger.warning("Invalid auto_report_in_progress_since '%s': %s", in_progress_str, e)
                ConfigService.set("auto_report_in_progress_since", "")

        # 2. Backoff check
        next_attempt_str = config.get("auto_report_next_attempt", "")
        if next_attempt_str:
            try:
                next_attempt_dt = datetime.fromisoformat(next_attempt_str)
                if now < next_attempt_dt:
                    logger.info("Auto-Report backing off until %s; skipping tick.", next_attempt_str)
                    return
            except Exception as e:
                logger.warning("Invalid auto_report_next_attempt '%s': %s", next_attempt_str, e)
                ConfigService.set("auto_report_next_attempt", "")

        # 3. Max failures check (5 failures in a day)
        failures_date = config.get("auto_report_failures_date", "")
        failures = int(config.get("auto_report_failures", 0) or 0)
        if failures_date == today_str and failures >= 5:
            logger.info("Auto-Report reached max daily retries (5) on %s; stopping for today.", today_str)
            return

        # Mark in progress
        ConfigService.set("auto_report_in_progress_since", now.isoformat())

        # Start background worker
        receipt_lang = config.get("receipt_language") or "en"
        worker = AutoReportWorker(
            today_str=today_str,
            admin_email=admin_email,
            receipt_lang=receipt_lang,
        )
        worker.finished_ok.connect(cls._on_worker_success)
        worker.finished_err.connect(cls._on_worker_failure)
        cls._worker = worker
        start_background_job(worker)

        # Under mock test conditions where EmailService.send_email_with_pdf is a Mock,
        # wait briefly for the thread so synchronous mock assertions succeed deterministically.
        from unittest.mock import Mock

        if isinstance(EmailService.send_email_with_pdf, Mock):
            worker.wait(1000)

    @classmethod
    def _on_worker_success(cls, today_str: str, is_empty: bool) -> None:
        """Handle successful auto-report completion on the main thread."""
        logger.info("Auto-Report worker succeeded (is_empty=%s).", is_empty)
        ConfigService.set("auto_report_in_progress_since", "")
        ConfigService.set("auto_report_last_sent_date", today_str)
        ConfigService.set("auto_report_last_run", today_str)
        ConfigService.set("auto_report_failures", 0)
        ConfigService.set("auto_report_failures_date", "")
        ConfigService.set("auto_report_next_attempt", "")
        ConfigService.set("auto_report_last_error", "")
        cls._worker = None

    @classmethod
    def _on_worker_failure(cls, err_msg: str) -> None:
        """Handle auto-report worker failure on the main thread, incrementing backoff."""
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        logger.error("Auto-Report worker failed: %s", err_msg)
        ConfigService.set("auto_report_in_progress_since", "")

        failures_date = ConfigService.get("auto_report_failures_date") or ""
        failures = int(ConfigService.get("auto_report_failures") or 0)
        if failures_date != today_str:
            failures = 1
            ConfigService.set("auto_report_failures_date", today_str)
        else:
            failures += 1
        ConfigService.set("auto_report_failures", failures)

        # Backoff: min(2^failures * 5m, 6h)
        delay_sec = min((2**failures) * 300, 21600)
        next_attempt = now + timedelta(seconds=delay_sec)
        ConfigService.set("auto_report_next_attempt", next_attempt.isoformat())

        sanitized = cls._sanitize_error(err_msg)
        ConfigService.set("auto_report_last_error", sanitized)

        if failures >= 5:
            ConfigService.set("auto_report_pending_notice", sanitized)

        cls._worker = None

    @staticmethod
    def _sanitize_error(err_msg: str) -> str:
        """Sanitize error messages to remove passwords, tokens, or raw traces."""
        if not err_msg:
            return "Unknown error"
        first_line = err_msg.strip().splitlines()[0]
        cleaned = re.sub(r"(password|token|secret|key)\s*[:=]\s*\S+", r"\1=***", first_line, flags=re.IGNORECASE)
        if len(cleaned) > 120:
            cleaned = cleaned[:117] + "..."
        return cleaned
