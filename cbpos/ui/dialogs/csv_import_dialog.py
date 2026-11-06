"""Dialog for CSV template download, column mapping preview, and product import."""

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.import_service import ImportError_, ImportService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.workers import CsvImportWorker

logger = logging.getLogger(__name__)

AVAILABLE_TARGET_FIELDS: list[tuple[str, str]] = [
    ("(ignore)", "import.ignore"),
    ("barcode", "import.field_barcode"),
    ("name_en", "import.field_name_en"),
    ("name_si", "import.field_name_si"),
    ("name_ta", "import.field_name_ta"),
    ("price", "import.field_price"),
    ("cost", "import.field_cost"),
    ("stock_qty", "import.field_stock_qty"),
    ("category", "import.field_category"),
    ("unit", "import.field_unit"),
    ("reorder_point", "import.field_reorder_point"),
]


class CsvImportDialog(QDialog):
    """Multi-step dialog: download template, choose file, map columns with preview, and import."""

    def __init__(self, import_service: ImportService, parent=None) -> None:
        """Initialize the dialog for CSV import."""
        super().__init__(parent)
        self.setWindowTitle(_t("csv_import.title"))
        self.setMinimumWidth(680)
        self.setMinimumHeight(520)
        self.setObjectName("CsvImportDialog")
        self.import_service = import_service
        self._selected_file: str = ""
        self._csv_worker: CsvImportWorker | None = None
        self._column_combos: dict[str, QComboBox] = {}
        self._total_rows: int = 0
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # --- Page 0: Choose File & Template ---
        self.page_choose = QWidget()
        self._init_choose_page()
        self.stack.addWidget(self.page_choose)

        # --- Page 1: Column Mapping & Preview ---
        self.page_preview = QWidget()
        self._init_preview_page()
        self.stack.addWidget(self.page_preview)

        self.retranslate_ui()

    def _init_choose_page(self) -> None:
        layout = QVBoxLayout(self.page_choose)
        layout.setSpacing(15)

        # Step 1: Template Download
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

        # Step 2: Choose File
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

        layout.addStretch()

        # Bottom buttons for Page 0
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel_p0 = QPushButton("")
        self.btn_cancel_p0.setProperty("class", "secondary")
        self.btn_cancel_p0.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel_p0)
        layout.addLayout(btn_layout)

    def _init_preview_page(self) -> None:
        layout = QVBoxLayout(self.page_preview)
        layout.setSpacing(12)

        self.lbl_map_title = QLabel("")
        self.lbl_map_title.setProperty("class", "bold")
        layout.addWidget(self.lbl_map_title)

        # Scroll area for mapping combos
        self.mapping_scroll = QScrollArea()
        self.mapping_scroll.setWidgetResizable(True)
        self.mapping_scroll.setMaximumHeight(180)
        self.mapping_container = QWidget()
        self.mapping_layout = QVBoxLayout(self.mapping_container)
        self.mapping_layout.setContentsMargins(5, 5, 5, 5)
        self.mapping_layout.setSpacing(6)
        self.mapping_scroll.setWidget(self.mapping_container)
        layout.addWidget(self.mapping_scroll)

        # First 5 rows table
        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.preview_table, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.result_label = QLabel("")
        self.result_label.setVisible(False)
        layout.addWidget(self.result_label)

        # Bottom buttons for Page 1
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_back = QPushButton("")
        self.btn_back.setProperty("class", "secondary")
        self.btn_back.clicked.connect(self._go_back)
        btn_layout.addWidget(self.btn_back)

        btn_layout.addStretch()

        self.btn_import = QPushButton("")
        self.btn_import.setObjectName("BtnImport")
        self.btn_import.setProperty("class", "primary")
        self.btn_import.clicked.connect(self._start_import)
        btn_layout.addWidget(self.btn_import)

        self.btn_cancel_p1 = QPushButton("")
        self.btn_cancel_p1.setObjectName("BtnCancel")
        self.btn_cancel_p1.setProperty("class", "secondary")
        self.btn_cancel_p1.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel_p1)

        layout.addLayout(btn_layout)

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("csv_import.title"))
        self.step1_label.setText(_t("csv_import.step1"))
        self.desc_label.setText(_t("csv_import.step1_description"))
        self.btn_download.setText(_t("csv_import.btn_download_template"))
        self.step2_label.setText(_t("csv_import.step2"))
        self.btn_choose.setText(_t("csv_import.btn_choose_file"))
        self.file_label.setText(
            _t("csv_import.no_file_selected") if not self._selected_file else Path(self._selected_file).name
        )
        self.btn_cancel_p0.setText(_t("common.cancel"))
        self.btn_cancel_p1.setText(_t("common.cancel"))
        self.btn_back.setText(_t("common.back"))
        self.lbl_map_title.setText(_t("import.map_title"))
        if self._total_rows > 0:
            self.btn_import.setText(_t("import.import_n", count=self._total_rows))
        else:
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
            QMessageBox.critical(
                self, _t("common.error"), _t("csv_import.template_save_error", error=translate_error(str(e)))
            )

    def _choose_file(self) -> None:
        """Open file picker for the CSV file and show preview."""
        file_path, _ = QFileDialog.getOpenFileName(self, _t("csv_import.select_csv_title"), "", "CSV Files (*.csv)")
        if not file_path:
            return

        self._selected_file = file_path
        self.file_label.setText(Path(file_path).name)

        try:
            headers, default_mapping, preview_rows, total_rows = self.import_service.parse_preview(file_path)
        except ImportError_ as e:
            if e.code == "file_unreadable":
                msg = _t("import.error_unreadable")
            elif e.code == "empty":
                msg = _t("import.error_empty")
            else:
                msg = str(e)
            QMessageBox.critical(self, _t("common.error"), msg)
            return
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
            return

        self._total_rows = total_rows
        self._populate_preview_page(headers, default_mapping, preview_rows)
        self.retranslate_ui()
        self.stack.setCurrentWidget(self.page_preview)

    def _populate_preview_page(
        self,
        headers: list[str],
        default_mapping: dict[str, str],
        preview_rows: list[dict[str, Any]],
    ) -> None:
        # Clear old mapping widgets
        while self.mapping_layout.count():
            item = self.mapping_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._column_combos.clear()

        # Build mapping rows
        for header in headers:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            lbl_header = QLabel(header)
            lbl_header.setMinimumWidth(160)
            row_layout.addWidget(lbl_header)

            lbl_arrow = QLabel("→")
            row_layout.addWidget(lbl_arrow)

            combo = QComboBox()
            combo.setMinimumWidth(180)
            for field_key, translation_key in AVAILABLE_TARGET_FIELDS:
                combo.addItem(_t(translation_key), field_key)

            # Pre-select matching field
            mapped_val = default_mapping.get(header, "(ignore)")
            idx = combo.findData(mapped_val)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentIndex(0)

            self._column_combos[header] = combo
            row_layout.addWidget(combo)
            row_layout.addStretch()

            self.mapping_layout.addWidget(row_widget)

        # Build preview table
        self.preview_table.clear()
        self.preview_table.setColumnCount(len(headers))
        self.preview_table.setHorizontalHeaderLabels(headers)
        self.preview_table.setRowCount(len(preview_rows))

        for r_idx, row in enumerate(preview_rows):
            for c_idx, header in enumerate(headers):
                val = str(row.get(header, ""))
                self.preview_table.setItem(r_idx, c_idx, QTableWidgetItem(val))

    def _go_back(self) -> None:
        """Return to page 0."""
        self.stack.setCurrentWidget(self.page_choose)

    def _get_current_mapping(self) -> dict[str, str]:
        """Extract user-selected column mappings from combo boxes."""
        return {header: combo.currentData() for header, combo in self._column_combos.items()}

    def _start_import(self) -> None:
        """Validate mappings and run the CSV import in a background thread."""
        if not self._selected_file:
            return

        mapping = self._get_current_mapping()

        # Check for duplicates among target fields
        target_to_header: dict[str, str] = {}
        for header, target in mapping.items():
            if target and target not in ("(ignore)", "ignore"):
                if target in target_to_header:
                    # Find translatable field name
                    field_label = target
                    for f_key, t_key in AVAILABLE_TARGET_FIELDS:
                        if f_key == target:
                            field_label = _t(t_key)
                            break
                    QMessageBox.warning(
                        self,
                        _t("common.validation_error"),
                        _t("import.duplicate_column", field=field_label),
                    )
                    return
                target_to_header[target] = header

        self.btn_import.setEnabled(False)
        self.btn_back.setEnabled(False)
        self.btn_import.setText(_t("csv_import.importing"))
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.result_label.setVisible(False)

        self._csv_worker = CsvImportWorker(self.import_service, self._selected_file, mapping=mapping)
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
        self.btn_back.setEnabled(True)
        self.btn_import.setEnabled(True)
        self.retranslate_ui()

        success = results.get("success", 0)
        failed = results.get("failed", 0)
        skipped = results.get("skipped", 0)
        errors = results.get("errors", [])

        summary = _t("csv_import.results", success=success, failed=failed, skipped=skipped)
        if errors:
            summary = f"{summary}\n" + "\n".join(errors[:5])
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
        self.btn_back.setEnabled(True)
        self.retranslate_ui()
        QMessageBox.critical(
            self, _t("csv_import.import_failed_title"), _t("csv_import.import_failed_message", error=error_msg)
        )
