"""
Background worker threads for long-running UI operations.

Keeps the main UI thread responsive during CSV imports, backups,
and report exports. All workers emit signals on completion or error
so the UI can react safely from the main thread.
"""

import html
import logging
import os
import re
import shutil
import tempfile
from typing import TYPE_CHECKING

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QTextDocument

if TYPE_CHECKING:
    from PyQt6.QtPrintSupport import QPrinter

logger = logging.getLogger(__name__)


class CsvImportWorker(QThread):
    """Imports products from a CSV file in a background thread."""

    result = pyqtSignal(dict)  # {"success": int, "failed": int, "skipped": int}
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # (current_row, total_rows)

    def __init__(self, import_service: object, file_path: str) -> None:
        """Set up the import job; QThread.finished deletes it once run() returns."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.import_service = import_service
        self.file_path = file_path

    def run(self) -> None:
        """Count CSV rows for progress reporting, then import products, emitting progress/result/error."""
        try:
            # Count rows with a lightweight line count (skip header)
            try:
                with open(self.file_path, encoding="utf-8-sig") as f:
                    total = max(0, sum(1 for _ in f) - 1)
            except Exception:
                total = 0

            results: dict[str, int] = self.import_service.import_products_from_csv_with_progress(
                self.file_path,
                progress_callback=lambda current: self.progress.emit(current, total),
            )

            self.result.emit(results)
        except Exception as e:
            logger.error("CSV import failed: %s", e)
            self.error.emit(str(e))


class BackupWorker(QThread):
    """Creates an encrypted database backup in a background thread."""

    result = pyqtSignal(str)  # backup_path
    error = pyqtSignal(str)

    def __init__(self, destination_dir: str, password: str) -> None:
        """Set up the backup job for the given destination directory and shop backup password."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.destination_dir = destination_dir
        self.password = password

    def run(self) -> None:
        """Create an encrypted backup and emit its path, or emit error on failure."""
        try:
            from cbpos.core.services.backup_service import BackupService

            backup_path = BackupService.create_backup(self.destination_dir, self.password)
            self.result.emit(backup_path)
        except Exception as e:
            logger.error("Backup failed: %s", e)
            self.error.emit(str(e))


class BackupListWorker(QThread):
    """Scans the backup directory in a background thread.

    list_backups() globs and stats every file in the backup directory --
    on the main thread this could still freeze the UI with zero feedback
    on a slow or network-mounted backup folder, the exact "takes time to
    show" symptom reported (#339), even though this page already uses
    this same worker-thread/LoadingOverlay pattern for every other
    operation.
    """

    result = pyqtSignal(list)
    # {"date": str | None, "restorable": bool} for the newest manual/auto
    # backup -- emitted before ``result`` (#619).
    status = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, backup_dir: str) -> None:
        """Set up the scan job for the given backup directory."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.backup_dir = backup_dir

    def run(self) -> None:
        """List backups and check the newest opens with the shop password, emitting the results or an error."""
        try:
            from cbpos.core.services.backup_service import BackupService
            from cbpos.core.services.config_service import ConfigService

            backups = BackupService.list_backups(self.backup_dir)
            self.status.emit(BackupService.last_backup_status(backups, ConfigService.get_backup_password()))
            self.result.emit(backups)
        except Exception as e:
            logger.error("Listing backups failed: %s", e)
            self.error.emit(str(e))


class RestoreWorker(QThread):
    """Restores a backup in a background thread."""

    result = pyqtSignal(bool)  # success
    # BackupError code -- the restore was refused before anything changed (#628)
    refused = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, backup_path: str, password: str) -> None:
        """Set up the restore job with the backup file and its password."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.backup_path = backup_path
        self.password = password

    def run(self) -> None:
        """Restore the given encrypted backup, emitting success/failure."""
        from cbpos.core.services.backup_service import BackupError, BackupService

        try:
            result = BackupService.restore_backup(self.backup_path, self.password)
            self.result.emit(result)
        except BackupError as e:
            logger.warning("Restore refused: %s", e)
            self.refused.emit(e.code)
        except Exception as e:
            logger.error("Restore failed: %s", e)
            self.error.emit(str(e))


class VerifyBackupWorker(QThread):
    """Verifies a backup (decrypt, CRC, database checks) in a background thread.

    Verifying extracts and checks the whole database, which froze the
    window on large backups when it ran on the UI thread (#629).
    """

    result = pyqtSignal(dict)  # BackupService.verify_backup() result

    def __init__(self, backup_path: str, password: str) -> None:
        """Set up the verify job with the backup file and its password."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.backup_path = backup_path
        self.password = password

    def run(self) -> None:
        """Verify the backup and emit the result dict (never raises)."""
        from cbpos.core.services.backup_service import BackupService

        try:
            outcome = BackupService.verify_backup(self.backup_path, self.password)
        except Exception as e:
            logger.error("Verify failed: %s", e)
            outcome = {"valid": False, "files": [], "size": "", "error": str(e), "error_code": None}
        self.result.emit(outcome)


class VacuumWorker(QThread):
    """Runs database VACUUM in a background thread."""

    result = pyqtSignal(dict)  # {size_before, size_after, saved}
    error = pyqtSignal(str)

    def __init__(self) -> None:
        """Set up the VACUUM job."""
        super().__init__()
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        """Run database VACUUM and emit the before/after/saved size stats."""
        try:
            from cbpos.core.services.maintenance_service import MaintenanceService

            result = MaintenanceService.vacuum_database()
            self.result.emit(result)
        except Exception as e:
            logger.error("Vacuum failed: %s", e)
            self.error.emit(str(e))


class PrinterTestWorker(QThread):
    """Sends a test slip to the receipt printer in a background thread."""

    result = pyqtSignal(object)  # HardwareTestResult

    def __init__(self, printer_type: str | None = None, printer_path: str | None = None) -> None:
        """Set up the test print job.

        Args:
            printer_type: Unsaved on-screen `PrinterType` to test, or None for the saved one.
            printer_path: Unsaved printer name / IP / VID:PID, or None for the saved one.
        """
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.printer_type = printer_type
        self.printer_path = printer_path

    def run(self) -> None:
        """Run the test print and emit its HardwareTestResult."""
        from cbpos.core.constants.hardware import PrinterError
        from cbpos.core.services.hardware_test_service import HardwareTestResult, HardwareTestService

        try:
            outcome = HardwareTestService.test_receipt_printer(self.printer_type, self.printer_path)
        except Exception as e:
            logger.error("Printer test worker failed: %s", e)
            outcome = HardwareTestResult(False, PrinterError.FAILED, detail=str(e))
        self.result.emit(outcome)


class DrawerTestWorker(QThread):
    """Kicks the cash drawer through the receipt printer in a background thread."""

    result = pyqtSignal(object)  # HardwareTestResult

    def __init__(
        self,
        printer_type: str | None = None,
        printer_path: str | None = None,
        pin: int | None = None,
    ) -> None:
        """Set up the drawer kick test job.

        Args:
            printer_type: Unsaved on-screen `PrinterType` to test, or None for the saved one.
            printer_path: Unsaved printer name / IP / VID:PID, or None for the saved one.
            pin: Drawer kick pin (2 or 5), or None for the saved one.
        """
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.printer_type = printer_type
        self.printer_path = printer_path
        self.pin = pin

    def run(self) -> None:
        """Run the drawer kick test and emit its HardwareTestResult."""
        from cbpos.core.constants.hardware import PrinterError
        from cbpos.core.services.hardware_test_service import HardwareTestResult, HardwareTestService

        try:
            outcome = HardwareTestService.test_cash_drawer(self.printer_type, self.printer_path, self.pin)
        except Exception as e:
            logger.error("Drawer test worker failed: %s", e)
            outcome = HardwareTestResult(False, PrinterError.FAILED, detail=str(e))
        self.result.emit(outcome)


class IntegrityCheckWorker(QThread):
    """Runs database integrity check in a background thread."""

    result = pyqtSignal(bool, str)  # (ok, message)

    def __init__(self) -> None:
        """Set up the database integrity check job."""
        super().__init__()
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        """Run the database integrity check and emit (ok, message)."""
        try:
            from cbpos.core.services.maintenance_service import MaintenanceService

            ok, message = MaintenanceService.integrity_check()
            self.result.emit(ok, message)
        except Exception as e:
            logger.error("Integrity check failed: %s", e)
            self.result.emit(False, str(e))


class ExportWorker(QThread):
    """Exports report data to Excel or PDF in a background thread."""

    result = pyqtSignal(str)  # success message
    error = pyqtSignal(str)

    def __init__(
        self,
        export_service: object,
        df: pd.DataFrame,
        filepath: str,
        report_name: str,
        fmt: str = "excel",
    ) -> None:
        """Set up the export job with the data, destination path, report name, and format."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.export_service = export_service
        self.df = df
        self.filepath = filepath
        self.report_name = report_name
        self.fmt = fmt

    def run(self) -> None:
        """Export the DataFrame to the requested format (excel/pdf/csv), emitting success or error."""
        try:
            if self.fmt == "excel":
                self.export_service.export_to_excel(self.df, self.filepath, self.report_name)
            elif self.fmt == "pdf":
                self.export_service.export_to_pdf(self.df, self.filepath, self.report_name)
            elif self.fmt == "csv":
                self.export_service.export_to_csv(self.df, self.filepath)
            self.result.emit("Export successful!")
        except Exception as e:
            logger.error("Export failed: %s", e)
            self.error.emit(str(e))


class AutocompleteLoadWorker(QThread):
    """Loads product names for the sales search box's autocomplete in a
    background thread. On a large inventory this DB query took 300-800ms
    run synchronously in SalesView.__init__, causing a visible freeze
    at startup and after every multi-user login switch."""

    result = pyqtSignal(list)  # list[str]

    def __init__(self, product_service, limit: int) -> None:
        """Set up the autocomplete-preload job for up to `limit` product names."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.product_service = product_service
        self.limit = limit

    def run(self) -> None:
        """Fetch top product names for autocomplete, emitting the list (or empty list on failure)."""
        try:
            names = self.product_service.get_top_products(self.limit)
            self.result.emit(names)
        except Exception as e:
            logger.error("Autocomplete load worker failed: %s", e)
            self.result.emit([])


_REPORT_PRINT_HTML = """
<html>
<head>
    <style>
        body {{ font-family: Helvetica, sans-serif; }}
        h1 {{ text-align: center; color: #001F3F; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th {{
            background-color: #00BCEB;
            color: white;
            padding: 8px;
            text-align: left;
        }}
        td {{
            padding: 8px;
            border-bottom: 1px solid #ddd;
        }}
        tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
    </style>
</head>
<body>
    <h1>{print_title}</h1>
    <p style="text-align: center;">
        {generated_on_label} {generated_on}
    </p>
    {table_html}
</body>
</html>
"""


def report_print_html(df: pd.DataFrame, title: str, generated_on_label: str) -> str:
    """Render a report DataFrame as the HTML page sent to the printer.

    Args:
        df: The full report data.
        title: Heading printed at the top (already translated).
        generated_on_label: Label before the timestamp (already translated).

    Returns:
        str: A complete HTML document.
    """
    return _REPORT_PRINT_HTML.format(
        print_title=html.escape(title),
        generated_on_label=html.escape(generated_on_label),
        generated_on=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        table_html=df.to_html(classes="table", index=False, border=0),
    )


class ReportPrintWorker(QThread):
    """Lays out a report and prints it in a background thread (#643).

    Building the HTML and laying out a large report froze the window when
    it ran on the UI thread. Qt supports painting on a QPrinter from a
    worker thread; the print dialog itself stays on the UI thread.

    ``result`` fires only once the whole document went to the printer
    without the printer reporting an error -- never on a guess.
    """

    result = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, printer: "QPrinter", df: pd.DataFrame, title: str, generated_on_label: str) -> None:
        """Set up the print job for a printer already chosen in the print dialog."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.printer = printer
        self.df = df
        self.title = title
        self.generated_on_label = generated_on_label

    def run(self) -> None:
        """Build the HTML, print it, and emit result -- or error if anything failed."""
        from PyQt6.QtPrintSupport import QPrinter

        try:
            document = QTextDocument()
            document.setHtml(report_print_html(self.df, self.title, self.generated_on_label))
            document.print(self.printer)
            if self.printer.printerState() in (QPrinter.PrinterState.Error, QPrinter.PrinterState.Aborted):
                raise RuntimeError(f"printer state {self.printer.printerState().name}")
            self.result.emit()
        except Exception as e:
            logger.error("Report print failed: %s", e)
            self.error.emit(str(e))


class ReportEmailWorker(QThread):
    """Exports a report to PDF and emails it in a background thread (#643).

    The PDF export and the SMTP send both blocked the UI thread, and the
    screen said "sending" before anything was known. ``result`` fires only
    once the mail server accepted the message.
    """

    result = pyqtSignal(str)  # recipient
    # (stage, detail): "export" -- the PDF failed; "not_configured" -- no
    # SMTP settings; "send" -- the server or network refused it.
    error = pyqtSignal(str, str)

    STAGE_EXPORT = "export"
    STAGE_NOT_CONFIGURED = "not_configured"
    STAGE_SEND = "send"

    def __init__(
        self,
        export_service: object,
        df: pd.DataFrame,
        report_name: str,
        to_email: str,
        subject: str,
        body: str,
    ) -> None:
        """Set up the email job: the report to attach and the message to send."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.export_service = export_service
        self.df = df
        self.report_name = report_name
        self.to_email = to_email
        self.subject = subject
        self.body = body

    def run(self) -> None:
        """Export the PDF to a private temp folder, send it, and always delete the temp copy."""
        from cbpos.core.services.email_service import EmailNotConfiguredError, deliver_email

        temp_dir = tempfile.mkdtemp(prefix="cbpos_report_")
        try:
            safe_name = re.sub(r"[^\w\-]+", "_", self.report_name).strip("_") or "report"
            filepath = os.path.join(temp_dir, f"{safe_name}.pdf")
            try:
                self.export_service.export_to_pdf(self.df, filepath, self.report_name)
            except Exception as e:
                logger.error("Report email: PDF export failed: %s", e)
                self.error.emit(self.STAGE_EXPORT, str(e))
                return

            try:
                deliver_email(self.to_email, self.subject, self.body, filepath)
            except EmailNotConfiguredError as e:
                self.error.emit(self.STAGE_NOT_CONFIGURED, str(e))
                return
            except Exception as e:
                logger.error("Report email: sending failed: %s", e)
                self.error.emit(self.STAGE_SEND, str(e))
                return

            self.result.emit(self.to_email)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
