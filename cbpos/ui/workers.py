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

    def __init__(self, import_service: object, file_path: str) -> None:
        super().__init__()
        self.import_service = import_service
        self.file_path = file_path

    def run(self) -> None:
        try:
            results: Dict[str, int] = self.import_service.import_products_from_csv(self.file_path)
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
        self.destination_dir = destination_dir

    def run(self) -> None:
        try:
            from cbpos.core.services.backup_service import BackupService

            backup_path, password = BackupService.create_backup(self.destination_dir)
            self.finished.emit(backup_path, password)
        except Exception as e:
            logger.error("Backup failed: %s", e)
            self.error.emit(str(e))


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
            self.finished.emit("Export successful!")
        except Exception as e:
            logger.error("Export failed: %s", e)
            self.error.emit(str(e))
