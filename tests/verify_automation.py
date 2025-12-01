import sys
from pathlib import Path

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from cbpos.core.services.scheduler_service import SchedulerService  # noqa: E402
from cbpos.core.services.email_service import EmailService  # noqa: E402
from cbpos.core.services.config_service import ConfigService  # noqa: E402
from cbpos.core.reports.definitions.cash_flow_report import CashFlowReport  # noqa: E402
from cbpos.core.database import Database  # noqa: E402
from PyQt6.QtCore import QCoreApplication  # noqa: E402


def test_config_persistence():
    print("\n--- Testing Config Persistence ---")
    ConfigService.set("auto_report_enabled", True)
    ConfigService.set("auto_report_time", "23:30")
    ConfigService.set("admin_email", "test@example.com")

    settings = ConfigService.get_all()
    assert settings["auto_report_enabled"] is True
    assert settings["auto_report_time"] == "23:30"
    assert settings["admin_email"] == "test@example.com"
    print("Config persistence passed.")


def test_scheduler_service():
    print("\n--- Testing Scheduler Service ---")
    scheduler = SchedulerService()
    print("Scheduler instantiated.")

    # Manually trigger check
    scheduler.check_schedule()
    print("check_schedule() called successfully.")

    # We can't easily test the full EOD process without mocking email/export,
    # but if check_schedule runs without error, basic wiring is correct.

    print("Scheduler service test passed.")


def test_email_service(app):
    print("\n--- Testing Email Service ---")
    # Mock SMTP config
    ConfigService.set("smtp_host", "smtp.example.com")
    ConfigService.set("smtp_port", "587")
    ConfigService.set("smtp_user", "user")
    ConfigService.set("smtp_pass", "pass")

    # We expect this to fail (or be mocked) since we don't have a real SMTP server.
    # But we want to ensure the QThread logic works.

    print("Sending test email...")
    worker = EmailService.send_email("recipient@example.com", "Test Subject", "Test Body")

    # Wait for signal
    def on_finished(success, message):
        print(f"Email finished: Success={success}, Message={message}")
        # It should fail with connection error, which is expected
        if not success:
            print("Expected failure (no real SMTP).")
        else:
            print("Unexpected success (did you have a real SMTP?).")

        app.quit()

    worker.finished.connect(on_finished)

    # Run event loop for a bit
    app.exec()
    print("Email service test completed.")


def test_cash_flow_report():
    print("\n--- Testing Cash Flow Report ---")
    Database()  # Initialize database
    report = CashFlowReport()

    # Generate report
    df = report.generate()
    print("Report Data Columns:", df.columns.tolist())
    print("Report Data:\n", df)

    assert "Category" in df.columns
    assert "Amount" in df.columns
    assert not df.empty

    # Check for specific categories
    categories = df["Category"].tolist()
    assert "Total Sales" in categories
    assert "Net Cash Flow" in categories

    print("Cash Flow Report generation passed.")


if __name__ == "__main__":
    app = QCoreApplication(sys.argv)

    try:
        test_config_persistence()
        test_cash_flow_report()
        test_scheduler_service()
        test_email_service(app)
        print("\nALL AUTOMATION TESTS PASSED")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback

        traceback.print_exc()
