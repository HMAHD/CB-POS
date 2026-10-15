"""Data Safety -> Export tab: write products, customers or sales to Excel/CSV."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.export_service import ExportService
from cbpos.i18n import _t
from cbpos.ui.utils.style_helpers import set_status_class
from cbpos.ui.views.data_safety.export_types import EXPORT_FORMATS, EXPORT_TYPES, ExportFormat, ExportType
from cbpos.ui.workers import ExportWorker, start_background_job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportContext:
    """What one running export needs to report its outcome (#695)."""

    filepath: str
    data_key: str
    row_count: int = 0


def _fill_choices(combo: QComboBox, choices: dict[str, ExportType] | dict[str, ExportFormat]) -> None:
    """(Re)label *combo* in the current language, keeping the chosen key."""
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    for choice in choices.values():
        combo.addItem(_t(choice.label_key), choice.key)
    combo.setCurrentIndex(max(combo.findData(current), 0))
    combo.blockSignals(False)


class ExportTabWidget(QWidget):
    """Pick a data type and format, choose a folder, export in the background."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the export form; the parent view drives ``retranslate_ui``."""
        super().__init__(parent)
        self._build_ui()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        self.lbl_export_desc = QLabel()
        self.lbl_export_desc.setProperty("class", "muted")
        self.lbl_export_desc.setWordWrap(True)
        layout.addWidget(self.lbl_export_desc)

        # One compact form instead of a full-width group box per dropdown (#618)
        self.lbl_export_section = QLabel()
        self.lbl_export_section.setObjectName("SettingsSectionTitle")
        layout.addWidget(self.lbl_export_section)

        self.export_form = QFormLayout()
        self.export_form.setVerticalSpacing(10)
        self.export_form.setHorizontalSpacing(16)
        self.export_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.export_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_export_label = QLabel()
        self.cmb_export_data = QComboBox()
        self.cmb_export_data.setFixedWidth(200)
        self.cmb_export_data.currentIndexChanged.connect(self._on_export_data_changed)
        self.export_form.addRow(self.lbl_export_label, self.cmb_export_data)

        self.lbl_fmt_label = QLabel()
        self.cmb_export_format = QComboBox()
        self.cmb_export_format.setFixedWidth(200)
        self.export_form.addRow(self.lbl_fmt_label, self.cmb_export_format)

        # Date range (visible only for Sales)
        self.lbl_export_from = QLabel()
        self.date_export_from = QDateEdit()
        self.date_export_from.setCalendarPopup(True)
        self.date_export_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_export_from.setDisplayFormat("yyyy-MM-dd")
        self.date_export_from.setFixedWidth(150)
        self.export_form.addRow(self.lbl_export_from, self.date_export_from)
        self.lbl_export_to = QLabel()
        self.date_export_to = QDateEdit()
        self.date_export_to.setCalendarPopup(True)
        self.date_export_to.setDate(QDate.currentDate())
        self.date_export_to.setDisplayFormat("yyyy-MM-dd")
        self.date_export_to.setFixedWidth(150)
        self.export_form.addRow(self.lbl_export_to, self.date_export_to)
        layout.addLayout(self.export_form)
        self._set_export_dates_visible(False)

        layout.addStretch()

        # Export button and status
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_do_export = QPushButton()
        self.btn_do_export.setProperty("class", "accent")
        self.btn_do_export.setFixedWidth(140)
        self.btn_do_export.clicked.connect(self._do_inline_export)
        btn_row.addWidget(self.btn_do_export)

        self.lbl_export_status = QLabel("")
        self.lbl_export_status.setWordWrap(True)
        btn_row.addWidget(self.lbl_export_status, 1)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_export_data_changed(self, _index: int = 0) -> None:
        """Show/hide date range based on selected data type."""
        self._set_export_dates_visible(self._export_type().needs_dates)

    def _set_export_dates_visible(self, visible: bool) -> None:
        """Show the From/To rows only when exporting Sales."""
        self.export_form.setRowVisible(self.date_export_from, visible)
        self.export_form.setRowVisible(self.date_export_to, visible)

    def _export_type(self) -> ExportType:
        return EXPORT_TYPES[self.cmb_export_data.currentData()]

    def _do_inline_export(self) -> None:
        """Export selected data type in the chosen format using a background thread."""
        export_type = self._export_type()
        export_format = EXPORT_FORMATS[self.cmb_export_format.currentData()]
        start = self.date_export_from.date().toPyDate()
        end = self.date_export_to.date().toPyDate()

        if export_type.needs_dates and start > end:
            QMessageBox.warning(
                self,
                _t("data_safety.export_invalid_date_title"),
                _t("data_safety.export_invalid_date_msg"),
            )
            return

        # Ask for output directory
        default_dir = str(Path.home() / "Documents")
        output_dir = QFileDialog.getExistingDirectory(self, _t("data_safety.export_choose_folder"), default_dir)
        if not output_dir:
            return

        self.btn_do_export.setEnabled(False)
        self.btn_do_export.setText(_t("data_safety.export_exporting"))
        self.lbl_export_status.setText("")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"{output_dir}/{export_type.stem}_{timestamp}{export_format.ext}"
        context = ExportContext(filepath=filepath, data_key=export_type.key, row_count=0)
        worker = ExportWorker(
            ExportService(),
            df=None,
            filepath=filepath,
            report_name=export_type.title,
            fmt=export_format.key,
            context=context,
            data_key=export_type.key,
            date_range=(start, end),
        )
        worker.exported.connect(self._on_export_finished)
        worker.error.connect(self._on_export_error)
        start_background_job(worker)  # outlives the view if it closes mid-export

    def _on_export_finished(self, context: ExportContext) -> None:
        """Handle successful export from background thread."""
        self.btn_do_export.setEnabled(True)
        self.btn_do_export.setText(_t("data_safety.export_btn"))
        label = _t(EXPORT_TYPES[context.data_key].label_key)
        self._set_export_status(
            "credit",
            _t(
                "data_safety.export_success",
                count=context.row_count,
                type=label.lower(),
                path=context.filepath,
            ),
        )

    def _on_export_error(self, error: str) -> None:
        """Handle export failure from background thread."""
        self.btn_do_export.setEnabled(True)
        self.btn_do_export.setText(_t("data_safety.export_btn"))
        self._set_export_status("debit", _t("data_safety.export_failed", error=error))

    def _set_export_status(self, css_class: str, text: str) -> None:
        """Update the export status label with the given class and text."""
        set_status_class(self.lbl_export_status, css_class, text)

    def retranslate_ui(self) -> None:
        """Update all translatable strings, keeping the chosen type and format."""
        self.lbl_export_desc.setText(_t("data_safety.export_desc"))
        self.lbl_export_section.setText(_t("data_safety.export_section"))
        self.lbl_export_label.setText(_t("data_safety.export_label"))
        _fill_choices(self.cmb_export_data, EXPORT_TYPES)
        self._on_export_data_changed()
        self.lbl_fmt_label.setText(_t("data_safety.export_format_label"))
        _fill_choices(self.cmb_export_format, EXPORT_FORMATS)
        self.lbl_export_from.setText(_t("data_safety.export_from"))
        self.lbl_export_to.setText(_t("data_safety.export_to"))
        self.btn_do_export.setText(_t("data_safety.export_btn"))
