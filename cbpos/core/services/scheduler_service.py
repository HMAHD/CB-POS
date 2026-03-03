import logging
import os
import tempfile
from datetime import datetime
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.email_service import EmailService
from cbpos.core.services.export_service import ExportService
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Service to handle background automation tasks (e.g. Auto-Reports).
    Should be called periodically (e.g. every minute) by a timer in the main app.
    """

    @staticmethod
    def check_automation():
        """
        Check if any automation tasks need to run.
        """
        config = ConfigService.get_all()

        # 1. Check Auto-Report
        if config.get("auto_report_enabled", False):
            SchedulerService._process_auto_report(config)

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

                if not df.empty:
                    # Generate PDF
                    export_service = ExportService()
                    temp_dir = tempfile.gettempdir()
                    filename = f"AutoReport_{today_str}.pdf"
                    filepath = os.path.join(temp_dir, filename)

                    export_service.export_to_pdf(df, filepath, f"Daily Sales Summary - {today_str}")

                    # Send Email
                    EmailService.send_email_with_pdf(
                        admin_email,
                        f"Daily Sales Report - {today_str}",
                        "Please find attached the daily sales summary.",
                        filepath,
                    )
                    logger.info("Auto-Report sent to %s", admin_email)

                # Update Last Run (even if empty, to avoid retrying every minute)
                ConfigService.set("auto_report_last_run", today_str)

            except Exception as e:
                logger.error("Auto-Report Failed: %s", e)
