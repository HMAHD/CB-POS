from PyQt6.QtCore import QObject, QTimer, QTime, QDate
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.email_service import EmailService
from cbpos.core.services.export_service import ExportService
from cbpos.core.reports.registry import ReportRegistry
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.core.reports.definitions.financial_reports import TaxLiabilityReport
import os
import tempfile


class SchedulerService(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_schedule)
        self.timer.start(60000)  # Check every minute
        self.registry = ReportRegistry()
        self.export_service = ExportService()

    def check_schedule(self):
        config = ConfigService.get_all()
        if not config.get("auto_report_enabled", False):
            return

        report_time_str = config.get("auto_report_time", "22:00")
        last_run_date_str = config.get("last_auto_report_date", "")
        try:
            report_time = QTime.fromString(report_time_str, "HH:mm")
            today = QDate.currentDate()

            # If already run today, skip
            if last_run_date_str == today.toString("yyyy-MM-dd"):
                return

            # If it's time (or past time) and hasn't run today
            now = QTime.currentTime()
            if now >= report_time:
                self.run_eod_process()

                # Update last run date
                ConfigService.set("last_auto_report_date", today.toString("yyyy-MM-dd"))

        except Exception as e:
            print(f"Scheduler Error: {e}")

    def run_eod_process(self):
        print("Running EOD Process...")
        config = ConfigService.get_all()
        admin_email = config.get("admin_email", "")

        if not admin_email:
            print("EOD Process Skipped: No Admin Email")
            return

        try:
            # 1. Generate Reports
            sales_report = DailySalesSummaryReport()
            tax_report = TaxLiabilityReport()

            # Filters for "Today"
            filters = {"date_range": {"start": QDate.currentDate().toPyDate(), "end": QDate.currentDate().toPyDate()}}

            df_sales = sales_report.generate(filters)
            df_tax = tax_report.generate(filters)

            # 2. Export to PDF
            temp_dir = tempfile.gettempdir()
            sales_pdf = os.path.join(
                temp_dir,
                f"EOD_Sales_{QDate.currentDate().toString('yyyyMMdd')}.pdf",
            )
            tax_pdf = os.path.join(
                temp_dir,
                f"EOD_Tax_{QDate.currentDate().toString('yyyyMMdd')}.pdf",
            )

            self.export_service.export_to_pdf(df_sales, sales_pdf, "Daily Sales Summary")
            self.export_service.export_to_pdf(df_tax, tax_pdf, "Tax Liability Report")

            # 3. Email
            body = f"Please find attached the End of Day reports for {QDate.currentDate().toString('yyyy-MM-dd')}."

            # Send Sales Report
            EmailService.send_email(
                admin_email, f"EOD Sales Report - " f"{QDate.currentDate().toString('yyyy-MM-dd')}", body, sales_pdf
            )

            # Send Tax Report
            EmailService.send_email(
                admin_email,
                f"EOD Tax Report - " f"{QDate.currentDate().toString('yyyy-MM-dd')}",
                body,
                tax_pdf,
            )

            print("EOD Process Completed: Emails Sent")

        except Exception as e:
            print(f"EOD Process Failed: {e}")
