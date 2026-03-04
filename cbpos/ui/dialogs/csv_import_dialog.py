"""
Dialog for CSV template download and product import.
"""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QProgressBar,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.import_service import ImportService
from cbpos.ui.workers import CsvImportWorker

logger = logging.getLogger(__name__)


class CsvImportDialog(QDialog):
    """Two-step dialog: download CSV template, then import filled CSV."""

    def __init__(self, import_service: ImportService, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Products from CSV")
        self.setMinimumWidth(480)
        self.setObjectName("CsvImportDialog")
        self.import_service = import_service
        self._selected_file: str = ""
        self._csv_worker = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # --- Step 1: Template Download ---
        step1_label = QLabel("Step 1: Download Template")
        step1_label.setProperty("class", "bold")
        layout.addWidget(step1_label)

        desc = QLabel(
            "Download the CSV template, fill in your product data,\n"
            "then import the completed file below."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_download = QPushButton("Download Template")
        btn_download.clicked.connect(self._download_template)
        layout.addWidget(btn_download)

        # Separator
        sep = QLabel("")
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #555;")
        layout.addWidget(sep)

        # --- Step 2: Import ---
        step2_label = QLabel("Step 2: Import Filled CSV")
        step2_label.setProperty("class", "bold")
        layout.addWidget(step2_label)

        file_layout = QHBoxLayout()
        self.btn_choose = QPushButton("Choose File")
        self.btn_choose.clicked.connect(self._choose_file)
        file_layout.addWidget(self.btn_choose)

        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: #888;")
        file_layout.addWidget(self.file_label, 1)
        layout.addLayout(file_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.result_label = QLabel("")
        self.result_label.setVisible(False)
        layout.addWidget(self.result_label)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_import = QPushButton("Import")
        self.btn_import.setProperty("class", "primary")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._start_import)
        btn_layout.addWidget(self.btn_import)

        layout.addLayout(btn_layout)

    def _download_template(self) -> None:
        """Save the CSV template to a user-chosen location."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CSV Template",
            str(Path.home() / "product_import_template.csv"),
            "CSV Files (*.csv)",
        )
        if not file_path:
            return

        try:
            content = ImportService.generate_template()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "Saved", f"Template saved to:\n{file_path}")
        except Exception as e:
            logger.error("Failed to save template: %s", e)
            QMessageBox.critical(self, "Error", f"Could not save template: {e}")

    def _choose_file(self) -> None:
        """Open file picker for the filled CSV."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")
        if file_path:
            self._selected_file = file_path
            self.file_label.setText(Path(file_path).name)
            self.file_label.setStyleSheet("")
            self.btn_import.setEnabled(True)

    def _start_import(self) -> None:
        """Run the CSV import in a background thread."""
        if not self._selected_file:
            return

        self.btn_import.setEnabled(False)
        self.btn_choose.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.result_label.setVisible(False)

        self._csv_worker = CsvImportWorker(self.import_service, self._selected_file)
        self._csv_worker.progress.connect(self._on_progress)
        self._csv_worker.finished.connect(self._on_finished)
        self._csv_worker.error.connect(self._on_error)
        self._csv_worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setMaximum(0)  # indeterminate

    def _on_finished(self, results: dict) -> None:
        self.progress_bar.setVisible(False)
        self.btn_choose.setEnabled(True)

        self.result_label.setText(
            f"Success: {results['success']}  |  "
            f"Failed: {results['failed']}  |  "
            f"Skipped: {results['skipped']}"
        )
        self.result_label.setVisible(True)

        QMessageBox.information(
            self,
            "Import Complete",
            f"Success: {results['success']}\n"
            f"Failed: {results['failed']}\n"
            f"Skipped (duplicates): {results['skipped']}",
        )
        self.accept()

    def _on_error(self, error_msg: str) -> None:
        self.progress_bar.setVisible(False)
        self.btn_import.setEnabled(True)
        self.btn_choose.setEnabled(True)
        QMessageBox.critical(self, "Import Failed", f"CSV import failed:\n{error_msg}")
