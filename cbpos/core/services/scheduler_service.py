import logging
import os
import tempfile
from datetime import datetime

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.email_service import EmailService
from cbpos.core.services.export_service import ExportService
from cbpos.i18n import translate_in

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MS = 60_000


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
            ConfigService.set("auto_report_last_error", "")
        else:
            logger.error("Auto-Report email failed: %s", message)
            ConfigService.set("auto_report_last_error", message)
            # Deliberately not marking last_run -- a failed send is
            # retried on a later tick instead of being silently treated
            # as done for the day.

    @staticmethod
    def _process_auto_report(config):
        report_time_str = config.get("auto_report_time", "22:00")
        last_run_str = config.get("auto_report_last_run", "")
        admin_email = config.get("admin_email", "")

        if not admin_email:
            return

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # If already run today, skip
        if last_run_str == today_str:
            return

        # Check time
        try:
            report_time = datetime.strptime(report_time_str, "%H:%M").time()
        except ValueError:
            return

        if now.time() >= report_time:
            # Run Report
            try:
                logger.info("Running Auto-Report...")
                report = DailySalesSummaryReport()
                # Generate for today
                filters = {"date_range": {"start": today_str, "end": today_str}}
                df = report.generate(filters)

                if df.empty:
                    # Nothing to report -- mark handled so we don't retry
                    # every minute for the rest of the day.
                    ConfigService.set("auto_report_last_run", today_str)
                    return

                # Generate PDF
                export_service = ExportService()
                temp_dir = tempfile.gettempdir()
                filename = f"AutoReport_{today_str}.pdf"
                filepath = os.path.join(temp_dir, filename)

                receipt_lang = config.get("receipt_language") or "en"
                pdf_title = translate_in(receipt_lang, "scheduler.daily_sales_title", date=today_str)
                export_service.export_to_pdf(df, filepath, pdf_title)

                # Send Email -- the send itself happens on a background
                # thread; auto_report_last_run is only advanced once the
                # callback confirms it actually succeeded (see
                # _flush_pending_email_result), not the moment it's fired.
                def _on_email_done(success: bool, message: str) -> None:
                    SchedulerService._pending_email_result = (success, message, today_str)

                subject = translate_in(receipt_lang, "scheduler.daily_sales_subject", date=today_str)
                body = translate_in(receipt_lang, "scheduler.daily_sales_body", website="ceybyte.com")

                EmailService.send_email_with_pdf(
                    admin_email,
                    subject,
                    body,
                    filepath,
                    callback=_on_email_done,
                )

            except Exception as e:
                logger.error("Auto-Report Failed: %s", e)
                ConfigService.set("auto_report_last_error", str(e))
