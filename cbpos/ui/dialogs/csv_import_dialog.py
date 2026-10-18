"""
Dialog for CSV template download and product import.
"""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.import_service import ImportService
from cbpos.i18n import _t
from cbpos.ui.workers import CsvImportWorker

logger = logging.getLogger(__name__)


class CsvImportDialog(QDialog):
    """Two-step dialog: download CSV template, then import filled CSV."""

    def __init__(self, import_service: ImportService, parent=None) -> None:
        """Initialize the dialog for template download and CSV import."""
        super().__init__(parent)
        self.setWindowTitle(_t("csv_import.title"))
        self.setMinimumWidth(480)
        self.setMinimumHeight(400)
        self.setObjectName("CsvImportDialog")
        self.import_service = import_service
        self._selected_file: str = ""
        self._csv_worker = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # --- Step 1: Template Download ---
        self.step1_label = QLabel("")
        self.step1_label.setProperty("class", "bold")
        layout.addWidget(self.step1_label)

        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        self.btn_download = QPushButton("")
        self.btn_download.clicked.connect(self._download_template)
        layout.addWidget(self.btn_download)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("CsvImportSeparator")
        layout.addWidget(sep)

        # --- Step 2: Import ---
        self.step2_label = QLabel("")
        self.step2_label.setProperty("class", "bold")
        layout.addWidget(self.step2_label)

        file_layout = QHBoxLayout()
        self.btn_choose = QPushButton("")
        self.btn_choose.clicked.connect(self._choose_file)
        file_layout.addWidget(self.btn_choose)

        self.file_label = QLabel("")
        self.file_label.setProperty("class", "muted")
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

        self.btn_cancel = QPushButton("")
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_import = QPushButton("")
        self.btn_import.setProperty("class", "primary")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._start_import)
        btn_layout.addWidget(self.btn_import)

        layout.addLayout(btn_layout)

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("csv_import.title"))
        self.step1_label.setText(_t("csv_import.step1"))
        self.desc_label.setText(_t("csv_import.step1_description"))
        self.btn_download.setText(_t("csv_import.btn_download_template"))
        self.step2_label.setText(_t("csv_import.step2"))
        self.btn_choose.setText(_t("csv_import.btn_choose_file"))
        self.file_label.setText(_t("csv_import.no_file_selected"))
        self.btn_cancel.setText(_t("common.cancel"))
        self.btn_import.setText(_t("csv_import.btn_import"))

    def _download_template(self) -> None:
        """Save the CSV template to a user-chosen location."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            _t("csv_import.save_template_title"),
            str(Path.home() / "product_import_template.csv"),
            "CSV Files (*.csv)",
        )
        if not file_path:
            return

        try:
            content = ImportService.generate_template()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, _t("common.saved"), _t("csv_import.template_saved", path=str(file_path)))
        except Exception as e:
            logger.error("Failed to save template: %s", e)
            QMessageBox.critical(self, _t("common.error"), _t("csv_import.template_save_error", error=str(e)))

    def _choose_file(self) -> None:
        """Open file picker for the filled CSV."""
        file_path, _ = QFileDialog.getOpenFileName(self, _t("csv_import.select_csv_title"), "", "CSV Files (*.csv)")
        if file_path:
            self._selected_file = file_path
            self.file_label.setText(Path(file_path).name)
            self.file_label.setProperty("class", "")
            self.btn_import.setEnabled(True)

    def _start_import(self) -> None:
        """Run the CSV import in a background thread."""
        if not self._selected_file:
            return

        self.btn_import.setEnabled(False)
        self.btn_import.setText(_t("csv_import.importing"))
        self.btn_choose.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.result_label.setVisible(False)

        self._csv_worker = CsvImportWorker(self.import_service, self._selected_file)
        self._csv_worker.progress.connect(self._on_progress)
        self._csv_worker.result.connect(self._on_finished)
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

        success = results["success"]
        failed = results["failed"]
        skipped = results["skipped"]
        summary = _t("csv_import.results", success=success, failed=failed, skipped=skipped)
        self.result_label.setText(summary)
        self.result_label.setVisible(True)

        QMessageBox.information(
            self,
            _t("csv_import.import_complete_title"),
            _t("csv_import.import_complete_message", success=success, failed=failed, skipped=skipped),
        )
        self.accept()

    def _on_error(self, error_msg: str) -> None:
        self.progress_bar.setVisible(False)
        self.btn_import.setEnabled(True)
        self.btn_import.setText(_t("csv_import.btn_import"))
        self.btn_choose.setEnabled(True)
        QMessageBox.critical(
            self, _t("csv_import.import_failed_title"), _t("csv_import.import_failed_message", error=error_msg)
        )
