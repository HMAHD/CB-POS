"""
Background worker threads for long-running UI operations.

Keeps the main UI thread responsive during CSV imports, backups,
and report exports. All workers emit signals on completion or error
so the UI can react safely from the main thread.
"""

import dataclasses
import html
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any

import pandas as pd
from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QTextDocument

from cbpos.core.utils.formatters import format_datetime

if TYPE_CHECKING:
    from PyQt6.QtPrintSupport import QPrinter

    from cbpos.core.services.export_service import ExportService

logger = logging.getLogger(__name__)

_RE_SAFE_FILENAME = re.compile(r"[^\w\-]+")


class _BackgroundJobs(QObject):
    """Holds running report workers so no view's lifetime decides theirs.

    A view used to own its worker through ``self._x_worker``. Destroying
    the view (logout, closing Management) while the job ran dropped that
    last reference, and Qt aborts the whole process when a running
    QThread is destroyed. Here each worker is held strongly until its
    ``finished`` signal arrives on the UI thread. The worker has no Qt
    parent, and its own ``finished -> deleteLater`` frees it afterwards.

    Results meant for a view that is gone are dropped by PyQt: a
    bound-method slot of a destroyed QObject receiver is disconnected.
    """

    def __init__(self) -> None:
        """Create the empty registry (on the UI thread, so its slot runs there)."""
        super().__init__()
        self._running: set[QThread] = set()

    def start(self, worker: QThread) -> None:
        """Keep *worker* alive until it finishes, then start it."""
        self._running.add(worker)
        worker.finished.connect(self._on_finished)
        worker.start()

    def _on_finished(self) -> None:
        """Drop the worker that just finished, and any other already done."""
        self._running.discard(self.sender())
        self._running = {w for w in self._running if not sip.isdeleted(w) and not w.isFinished()}

    def running(self) -> list[QThread]:
        """Workers still held (started and not yet seen to finish)."""
        return [w for w in self._running if not sip.isdeleted(w)]

    def wait_all(self, timeout_ms: int) -> None:
        """Wait up to *timeout_ms* in total for running workers, on app exit.

        A worker still running after that is handed to C++ ownership, so
        Python tearing down its wrapper at exit never destroys the running
        thread (the abort this registry exists to prevent).
        """
        deadline_ms = max(timeout_ms, 0)
        for worker in self.running():
            timer_start = time.monotonic()
            if not worker.wait(deadline_ms):
                logger.warning("Background job %s still running at exit; leaving it.", type(worker).__name__)
                sip.transferto(worker, None)
            deadline_ms = max(0, deadline_ms - int((time.monotonic() - timer_start) * 1000))
        self._running.clear()


_jobs: _BackgroundJobs | None = None


def _registry() -> _BackgroundJobs:
    global _jobs
    if _jobs is None:
        _jobs = _BackgroundJobs()
    return _jobs


def start_background_job(worker: QThread) -> None:
    """Start *worker*, kept alive independently of whoever started it.

    Use for a worker a view starts and might outlive -- never hold it only
    in ``self._worker`` and call ``start()`` directly. Call from the UI thread.
    """
    _registry().start(worker)


def running_background_jobs() -> list[QThread]:
    """Workers started with ``start_background_job`` that haven't finished yet."""
    return _jobs.running() if _jobs is not None else []


def wait_for_background_jobs(timeout_ms: int = 3000) -> None:
    """On app exit: give running background jobs a short time to finish."""
    if _jobs is not None:
        _jobs.wait_all(timeout_ms)


class CsvImportWorker(QThread):
    """Imports products from a CSV file in a background thread."""

    result = pyqtSignal(dict)  # {"success": int, "failed": int, "skipped": int}
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # (current_row, total_rows)

    def __init__(
        self,
        import_service: object,
        file_path: str,
        mapping: dict[str, str] | None = None,
    ) -> None:
        """Set up the import job; QThread.finished deletes it once run() returns."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.import_service = import_service
        self.file_path = file_path
        self.mapping = mapping

    def run(self) -> None:
        """Import products, emitting progress/result/error."""
        try:
            results: dict[str, int] = self.import_service.import_products_from_csv_with_progress(
                self.file_path,
                progress_callback=lambda current: self.progress.emit(current, 0),
                mapping=self.mapping,
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
    exported = pyqtSignal(object)  # the caller's ``context``, on success only
    error = pyqtSignal(str)

    def __init__(
        self,
        export_service: "ExportService",
        df: pd.DataFrame | None = None,
        filepath: str = "",
        report_name: str = "",
        fmt: str = "excel",
        context: object = None,
        data_key: str | None = None,
        date_range: tuple | None = None,
    ) -> None:
        """Set up the export job with the data, destination path, report name, and format.

        Args:
            context: Anything the caller needs back when the export succeeds;
                emitted unchanged through ``exported`` so the caller keeps no
                per-export state of its own.
            data_key: Optional export type key (e.g. 'products', 'customers', 'sales').
                When `df` is None, `ExportWorker` loads the data off the UI thread
                using `EXPORT_TYPES[data_key].fetch(*date_range)` (#748).
            date_range: Optional `(start, end)` tuple passed to `fetch` when `data_key` is used.
        """
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.export_service = export_service
        self.df = df
        self.filepath = filepath
        self.report_name = report_name
        self.fmt = fmt
        self.context = context
        self.data_key = data_key
        self.date_range = date_range

    def run(self) -> None:
        """Export the DataFrame to the requested format (excel/pdf/csv), emitting success or error."""
        try:
            if self.df is not None:
                df = self.df
            elif self.data_key:
                from cbpos.ui.views.data_safety.export_types import EXPORT_TYPES

                export_type = EXPORT_TYPES[self.data_key]
                start, end = self.date_range if self.date_range else (None, None)
                df = export_type.fetch(start, end)
            else:
                raise ValueError("ExportWorker requires either df or data_key")

            if self.fmt == "excel":
                self.export_service.export_to_excel(df, self.filepath, self.report_name)
            elif self.fmt == "pdf":
                self.export_service.export_to_pdf(df, self.filepath, self.report_name)
            elif self.fmt == "csv":
                self.export_service.export_to_csv(df, self.filepath)

            context = self.context
            if dataclasses.is_dataclass(context) and hasattr(context, "row_count"):
                context = dataclasses.replace(context, row_count=len(df))

            self.result.emit("Export successful!")
            self.exported.emit(context)
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


class LabelProductLoaderWorker(QThread):
    """Loads active products for LabelPrintDialog in a background thread (#819)."""

    loaded = pyqtSignal(list)

    def __init__(self, product_service) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.product_service = product_service

    def run(self) -> None:
        """Fetch all active products and emit the result list."""
        try:
            products = self.product_service.get_all_products()
            self.loaded.emit(products)
        except Exception as e:
            logger.debug("LabelProductLoaderWorker failed: %s", e)
            self.loaded.emit([])


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
        generated_on=format_datetime(pd.Timestamp.now().to_pydatetime()),
        table_html=df.to_html(classes="table", index=False, border=0),
    )


def _parse_bool(val: Any) -> bool:
    """Safely parse boolean configuration values."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "on")
    return bool(val)


class ReportPrintWorker(QThread):
    """Lays out a report and prints it in a background thread (#643, #731).

    Building the HTML and laying out a large report froze the window when
    it ran on the UI thread. Qt supports painting on a QPrinter from a
    worker thread; the print dialog itself stays on the UI thread.

    When ``report_print_main_thread_final`` is enabled, layout and document
    preparation still happen in the background thread, but the final
    ``print()`` invocation is dispatched to the main thread via a queued
    signal (#731 defensive fallback).

    ``result`` fires only once the whole document went to the printer
    without the printer reporting an error -- never on a guess.
    """

    result = pyqtSignal()
    error = pyqtSignal(str)
    _request_main_thread_print = pyqtSignal(object)

    def __init__(
        self,
        printer: "QPrinter",
        df: pd.DataFrame,
        title: str,
        generated_on_label: str,
        main_thread_final: bool | None = None,
    ) -> None:
        """Set up the print job for a printer already chosen in the print dialog."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.printer = printer
        self.df = df
        self.title = title
        self.generated_on_label = generated_on_label
        if main_thread_final is None:
            from cbpos.core.services.config_service import ConfigService

            self.main_thread_final = _parse_bool(ConfigService.get("report_print_main_thread_final"))
        else:
            self.main_thread_final = _parse_bool(main_thread_final)

        self._request_main_thread_print.connect(self._do_main_thread_print)
        self._main_thread_done = threading.Event()
        self._main_thread_failed = False
        self._main_thread_err: str | None = None
        self._doc: QTextDocument | None = None

    def run(self) -> None:
        """Build the HTML, print it, and emit result -- or error if anything failed."""
        from PyQt6.QtPrintSupport import QPrinter

        try:
            if hasattr(self.printer, "isValid") and not self.printer.isValid():
                raise RuntimeError("printer is invalid or offline")

            document = QTextDocument()
            document.setHtml(report_print_html(self.df, self.title, self.generated_on_label))

            if self.main_thread_final:
                self._doc = document
                document.moveToThread(self.thread())
                self._main_thread_failed = False
                self._main_thread_err = None
                self._main_thread_done.clear()
                self._request_main_thread_print.emit(document)
                if not self._main_thread_done.wait(timeout=30):
                    raise RuntimeError("Timed out waiting for main-thread report printing")
                if self._main_thread_failed:
                    raise RuntimeError(self._main_thread_err or "Main thread report printing failed")
            else:
                document.print(self.printer)
                if hasattr(self.printer, "printerState") and self.printer.printerState() in (
                    QPrinter.PrinterState.Error,
                    QPrinter.PrinterState.Aborted,
                ):
                    raise RuntimeError(f"printer state {self.printer.printerState().name}")

            self.result.emit()
        except Exception as e:
            logger.error("Report print failed: %s", e)
            self.error.emit(str(e))

    def _do_main_thread_print(self, document: QTextDocument) -> None:
        from PyQt6.QtPrintSupport import QPrinter

        try:
            if hasattr(self.printer, "isValid") and not self.printer.isValid():
                raise RuntimeError("printer is invalid or offline")
            document.print(self.printer)
            if hasattr(self.printer, "printerState") and self.printer.printerState() in (
                QPrinter.PrinterState.Error,
                QPrinter.PrinterState.Aborted,
            ):
                raise RuntimeError(f"printer state {self.printer.printerState().name}")
        except Exception as e:
            self._main_thread_failed = True
            self._main_thread_err = str(e) or type(e).__name__
        finally:
            self._main_thread_done.set()


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
        export_service: "ExportService",
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
            safe_name = _RE_SAFE_FILENAME.sub("_", self.report_name).strip("_") or "report"
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


class SyncTestWorker(QThread):
    """Tests connection to sync server in a background thread."""

    # success: bool, outcome: str, info: dict
    finished_result = pyqtSignal(bool, str, dict)

    def __init__(self, address: str, secret: str) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.address = address
        self.secret = secret

    def run(self) -> None:
        """Test the heartbeat endpoint of the sync server and emit result signals."""
        import json
        import ssl
        import urllib.error
        import urllib.request
        from urllib.parse import urlsplit

        from cbpos.core.services.config_service import ConfigService
        from cbpos.infrastructure.sync_tls import (
            build_client_ssl_context,
            cert_fingerprint,
            fetch_server_certificate,
        )

        address = self.address
        if address.startswith("http://"):
            address = "https://" + address[len("http://") :]
        elif not address.startswith("https://"):
            address = f"https://{address}"

        parsed = urlsplit(address)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5555

        pinned_pem = ConfigService.get("sync_pinned_cert_pem")
        if not pinned_pem:
            # Not paired yet: test connection by zero-token fetching server certificate
            try:
                pem = fetch_server_certificate(host, port, timeout=5.0)
                fp = cert_fingerprint(pem)
                self.finished_result.emit(
                    True, "unpaired", {"fingerprint": fp, "address": address, "host": host, "port": port}
                )
                return
            except Exception as e:
                logger.debug("Sync test pre-fetch failed: %s", e)
                self.finished_result.emit(False, "failed", {"error": str(e), "address": address})
                return

        url = f"{address}/sync/heartbeat"
        try:
            client_ctx = build_client_ssl_context(pinned_pem)
            req = urllib.request.Request(url, method="GET", headers={"X-Sync-Token": self.secret})
            with urllib.request.urlopen(req, timeout=5, context=client_ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("status") == "ok":
                version = data.get("protocol_version", "?")
                terminals = data.get("terminals_connected", 0)
                self.finished_result.emit(True, "ok", {"version": version, "terminals": terminals})
            else:
                self.finished_result.emit(False, "unexpected", {})
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.finished_result.emit(False, "unauthorized", {})
            else:
                self.finished_result.emit(False, "failed", {"error": str(e), "address": address})
        except (urllib.error.URLError, ssl.SSLCertVerificationError) as e:
            err_str = str(e)
            if hasattr(e, "reason"):
                err_str += f" {e.reason}"
            if "CERTIFICATE_VERIFY_FAILED" in err_str or "certificate verify failed" in err_str.lower():
                self.finished_result.emit(
                    False, "cert_mismatch", {"error": err_str, "address": address, "host": host, "port": port}
                )
            else:
                self.finished_result.emit(False, "failed", {"error": str(e), "address": address})
        except Exception as e:
            err_str = str(e)
            if "CERTIFICATE_VERIFY_FAILED" in err_str or "certificate verify failed" in err_str.lower():
                self.finished_result.emit(
                    False, "cert_mismatch", {"error": err_str, "address": address, "host": host, "port": port}
                )
            else:
                logger.exception("Sync test error: %s", e)
                self.finished_result.emit(False, "error", {"error": str(e)})


class ReloadCatalogWorker(QThread):
    """Performs a full catalog pull/replacement from the Main PC in a background thread."""

    finished_result = pyqtSignal(bool, str)

    def __init__(self, terminal_id: str, server_address: str, shared_secret: str) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.terminal_id = terminal_id
        self.server_address = server_address
        self.shared_secret = shared_secret

    def run(self) -> None:
        """Run full catalog reload in background."""
        from cbpos.infrastructure.sync_client import SyncClient

        try:
            client = SyncClient(
                terminal_id=self.terminal_id,
                server_address=self.server_address,
                shared_secret=self.shared_secret,
            )
            client.reload_ssl_context()
            res = client._pull_catalog(full_sync=True)
            if res >= 0:
                self.finished_result.emit(True, "")
            else:
                self.finished_result.emit(False, client.error_code() or "catalog_apply_failed")
        except Exception as e:
            logger.error("ReloadCatalogWorker failed: %s", e)
            self.finished_result.emit(False, str(e))


class PinCheckWorker(QThread):
    """Background worker thread for asynchronous bcrypt PIN verification (#917).

    Executes CPU-intensive bcrypt hashing off the Qt UI thread for:
    - mode="login": calls AuthService.login(pin)
    - mode="authenticate": calls AuthService.authenticate_pin(pin)
    - mode="check_own": calls AuthService.check_own_pin(user_id, pin)

    Emits `result` with the outcome (User | None, or bool).
    """

    result = pyqtSignal(object)

    def __init__(
        self,
        mode: str,
        pin: str,
        user_id: int | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.pin = pin
        self.user_id = user_id
        self.output: Any = None

    def run(self) -> None:
        """Run the PIN verification off the UI thread."""
        from cbpos.core.services.auth_service import AuthService

        try:
            if self.mode == "login":
                self.output = AuthService.login(self.pin)
            elif self.mode == "authenticate":
                self.output = AuthService.authenticate_pin(self.pin)
            elif self.mode == "check_own":
                if self.user_id is None:
                    raise ValueError("user_id required for check_own mode")
                self.output = AuthService.check_own_pin(self.user_id, self.pin)
            else:
                raise ValueError(f"Unknown PIN check mode: {self.mode}")
        except Exception as e:
            logger.exception("PinCheckWorker failed in mode %s: %s", self.mode, e)
            self.output = False if self.mode == "check_own" else None
        self.result.emit(self.output)


class TaxInvoiceArtifactWorker(QThread):
    """Generates and finalizes a VAT Tax Invoice PDF artifact in a background thread."""

    result = pyqtSignal(object)  # TaxInvoiceArtifactResult
    error = pyqtSignal(str)

    def __init__(
        self,
        invoice_id: int,
        destination_path: str,
        user_id: int,
        channel: str = "pdf",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.finished.connect(self.deleteLater)
        self.invoice_id = invoice_id
        self.destination_path = destination_path
        self.user_id = user_id
        self.channel = channel

    def run(self) -> None:
        """Execute artifact issuance off the Qt UI thread."""
        try:
            from cbpos.core.services.tax_invoice_service import TaxInvoiceService

            artifact = TaxInvoiceService.issue_artifact(
                invoice_id=self.invoice_id,
                destination_path=self.destination_path,
                user_id=self.user_id,
                channel=self.channel,
            )
            self.result.emit(artifact)
        except Exception as e:
            logger.exception("Tax invoice artifact generation failed: %s", e)
            self.error.emit(str(e))


# Alias PrintWorker as ReceiptWorker for backwards/audit naming compatibility
def __getattr__(name: str):
    if name == "ReceiptWorker":
        from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

        return PrintWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
