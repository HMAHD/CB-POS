"""
Background worker threads for long-running UI operations.

Keeps the main UI thread responsive during CSV imports, backups,
and report exports. All workers emit signals on completion or error
so the UI can react safely from the main thread.
"""

import logging
from typing import Dict

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class CsvImportWorker(QThread):
    """Imports products from a CSV file in a background thread."""

    finished = pyqtSignal(dict)  # {"success": int, "failed": int, "skipped": int}
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # (current_row, total_rows)

    def __init__(self, import_service: object, file_path: str) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.error.connect(self.deleteLater)
        self.import_service = import_service
        self.file_path = file_path

    def run(self) -> None:
        try:
            # Count rows with a lightweight line count (skip header)
            try:
                with open(self.file_path, "r", encoding="utf-8-sig") as f:
                    total = max(0, sum(1 for _ in f) - 1)
            except Exception:
                total = 0

            results: Dict[str, int] = self.import_service.import_products_from_csv_with_progress(
                self.file_path,
                progress_callback=lambda current: self.progress.emit(current, total),
            )

            self.finished.emit(results)
        except Exception as e:
            logger.error("CSV import failed: %s", e)
            self.error.emit(str(e))


class BackupWorker(QThread):
    """Creates an encrypted database backup in a background thread."""

    finished = pyqtSignal(str, str)  # (backup_path, password)
    error = pyqtSignal(str)

    def __init__(self, destination_dir: str) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.error.connect(self.deleteLater)
        self.destination_dir = destination_dir

    def run(self) -> None:
        try:
            from cbpos.core.services.backup_service import BackupService

            backup_path, password = BackupService.create_backup(self.destination_dir)
            self.finished.emit(backup_path, password)
        except Exception as e:
            logger.error("Backup failed: %s", e)
            self.error.emit(str(e))


class RestoreWorker(QThread):
    """Restores a backup in a background thread."""

    finished = pyqtSignal(bool)  # success
    error = pyqtSignal(str)

    def __init__(self, backup_path: str, password: str) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.error.connect(self.deleteLater)
        self.backup_path = backup_path
        self.password = password

    def run(self) -> None:
        try:
            from cbpos.core.services.backup_service import BackupService

            result = BackupService.restore_backup(self.backup_path, self.password)
            self.finished.emit(result)
        except Exception as e:
            logger.error("Restore failed: %s", e)
            self.error.emit(str(e))


class VacuumWorker(QThread):
    """Runs database VACUUM in a background thread."""

    finished = pyqtSignal(dict)  # {size_before, size_after, saved}
    error = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.error.connect(self.deleteLater)

    def run(self) -> None:
        try:
            from cbpos.core.services.maintenance_service import MaintenanceService

            result = MaintenanceService.vacuum_database()
            self.finished.emit(result)
        except Exception as e:
            logger.error("Vacuum failed: %s", e)
            self.error.emit(str(e))


class PrinterTestWorker(QThread):
    """Tests receipt printer connectivity in a background thread."""

    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        try:
            from cbpos.core.services.hardware_test_service import HardwareTestService

            success, message = HardwareTestService.test_receipt_printer()
            self.finished.emit(success, message)
        except Exception as e:
            logger.error("Printer test worker failed: %s", e)
            self.finished.emit(False, str(e))


class DrawerTestWorker(QThread):
    """Tests cash drawer kick in a background thread."""

    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        try:
            from cbpos.core.services.hardware_test_service import HardwareTestService

            success, message = HardwareTestService.test_cash_drawer()
            self.finished.emit(success, message)
        except Exception as e:
            logger.error("Drawer test worker failed: %s", e)
            self.finished.emit(False, str(e))


class IntegrityCheckWorker(QThread):
    """Runs database integrity check in a background thread."""

    finished = pyqtSignal(bool, str)  # (ok, message)

    def __init__(self) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        try:
            from cbpos.core.services.maintenance_service import MaintenanceService

            ok, message = MaintenanceService.integrity_check()
            self.finished.emit(ok, message)
        except Exception as e:
            logger.error("Integrity check failed: %s", e)
            self.finished.emit(False, str(e))


class ExportWorker(QThread):
    """Exports report data to Excel or PDF in a background thread."""

    finished = pyqtSignal(str)  # success message
    error = pyqtSignal(str)

    def __init__(
        self,
        export_service: object,
        df: pd.DataFrame,
        filepath: str,
        report_name: str,
        fmt: str = "excel",
    ) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.error.connect(self.deleteLater)
        self.export_service = export_service
        self.df = df
        self.filepath = filepath
        self.report_name = report_name
        self.fmt = fmt

    def run(self) -> None:
        try:
            if self.fmt == "excel":
                self.export_service.export_to_excel(self.df, self.filepath, self.report_name)
            elif self.fmt == "pdf":
                self.export_service.export_to_pdf(self.df, self.filepath, self.report_name)
            elif self.fmt == "csv":
                self.export_service.export_to_csv(self.df, self.filepath)
            self.finished.emit("Export successful!")
        except Exception as e:
            logger.error("Export failed: %s", e)
            self.error.emit(str(e))
