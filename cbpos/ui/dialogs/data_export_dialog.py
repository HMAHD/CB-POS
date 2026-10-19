"""
Data Export dialog for CB-POS.

Allows users to select which data to export (Products, Customers, Sales),
choose a format (CSV, Excel, PDF), pick a date range for sales,
and export to a chosen directory.

Uses QSS objectNames/class properties for theme compatibility.
"""

import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.data_export_service import DataExportService
from cbpos.core.services.export_service import ExportService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class DataExportDialog(QDialog):
    """Dialog for exporting Products, Customers, and Sales data."""

    def __init__(self, parent=None):
        """Initialize the dialog with default data selection and export options."""
        super().__init__(parent)
        self.setWindowTitle(_t("data_export.title"))
        self.setMinimumSize(520, 480)
        self.resize(560, 500)
        self._init_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel(_t("data_export.heading"))
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        desc = QLabel(_t("data_export.description"))
        desc.setProperty("class", "muted")
        layout.addWidget(desc)

        # Data selection
        grp_data = QGroupBox(_t("data_export.select_data"))
        data_layout = QVBoxLayout(grp_data)
        data_layout.setSpacing(10)

        self.chk_products = QCheckBox(_t("data_export.products"))
        self.chk_products.setChecked(True)
        data_layout.addWidget(self.chk_products)

        self.chk_customers = QCheckBox(_t("data_export.customers"))
        data_layout.addWidget(self.chk_customers)

        self.chk_sales = QCheckBox(_t("data_export.sales"))
        self.chk_sales.setChecked(True)
        self.chk_sales.toggled.connect(self._toggle_date_range)
        data_layout.addWidget(self.chk_sales)

        layout.addWidget(grp_data)

        # Date range for sales
        self.grp_dates = QGroupBox(_t("data_export.sales_date_range"))
        dates_form = QFormLayout(self.grp_dates)
        dates_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        dates_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        dates_form.setVerticalSpacing(10)
        dates_form.setHorizontalSpacing(16)

        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addMonths(-1))
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        dates_form.addRow(_t("common.from"), self.date_start)

        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        dates_form.addRow(_t("common.to"), self.date_end)

        layout.addWidget(self.grp_dates)

        # Format selector
        grp_format = QGroupBox(_t("data_export.output_format"))
        fmt_layout = QHBoxLayout(grp_format)

        self.cmb_format = QComboBox()
        self.cmb_format.addItem(_t("data_export.format_excel"), "excel")
        self.cmb_format.addItem(_t("data_export.format_csv"), "csv")
        self.cmb_format.addItem(_t("data_export.format_pdf"), "pdf")
        self.cmb_format.setFixedWidth(200)
        fmt_layout.addWidget(self.cmb_format)
        fmt_layout.addStretch()

        layout.addWidget(grp_format)
        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_export = QPushButton(_t("common.export"))
        self.btn_export.setObjectName("BtnExport")
        self.btn_export.setProperty("class", "accent")
        self.btn_export.setFixedWidth(140)
        self.btn_export.clicked.connect(self._do_export)
        btn_layout.addWidget(self.btn_export)

        btn_cancel = QPushButton(_t("common.cancel"))
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.setProperty("class", "secondary")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def _toggle_date_range(self, checked: bool) -> None:
        self.grp_dates.setVisible(checked)

    def _do_export(self) -> None:
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.REPORTS_EXPORT, self):
            return

        if not any([self.chk_products.isChecked(), self.chk_customers.isChecked(), self.chk_sales.isChecked()]):
            QMessageBox.warning(self, _t("data_export.no_data_title"), _t("data_export.no_data_msg"))
            return

        # Ask for output directory
        default_dir = str(Path.home() / "Documents")
        output_dir = QFileDialog.getExistingDirectory(self, _t("data_export.choose_folder"), default_dir)
        if not output_dir:
            return

        self.btn_export.setEnabled(False)
        self.btn_export.setText(_t("data_export.exporting"))
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        try:
            export_svc = ExportService()
            fmt = self.cmb_format.currentData()

            ext_map = {"excel": ".xlsx", "csv": ".csv", "pdf": ".pdf"}
            ext = ext_map.get(fmt, ".xlsx")

            exported = []
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if self.chk_products.isChecked():
                df = DataExportService.get_products_dataframe()
                filepath = f"{output_dir}/products_{timestamp}{ext}"
                self._write_export(export_svc, df, filepath, _t("data_export.products"), fmt)
                exported.append(_t("data_export.export_row_summary", type=_t("data_export.products"), count=len(df)))

            if self.chk_customers.isChecked():
                df = DataExportService.get_customers_dataframe()
                filepath = f"{output_dir}/customers_{timestamp}{ext}"
                self._write_export(export_svc, df, filepath, _t("data_export.customers"), fmt)
                exported.append(_t("data_export.export_row_summary", type=_t("data_export.customers"), count=len(df)))

            if self.chk_sales.isChecked():
                start = self.date_start.date().toPyDate()
                end = self.date_end.date().toPyDate()
                start_dt = datetime(start.year, start.month, start.day, 0, 0, 0)
                end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)
                df = DataExportService.get_sales_dataframe(start_dt, end_dt)
                filepath = f"{output_dir}/sales_{timestamp}{ext}"
                self._write_export(export_svc, df, filepath, _t("data_export.sales"), fmt)
                exported.append(_t("data_export.export_row_summary", type=_t("data_export.sales"), count=len(df)))

            QApplication.restoreOverrideCursor()
            self.btn_export.setEnabled(True)
            self.btn_export.setText(_t("common.export"))

            QMessageBox.information(
                self,
                _t("data_export.complete_title"),
                _t("data_export.complete_msg")
                + "\n\n"
                + "\n".join(f"  {e}" for e in exported)
                + f"\n\n{_t('data_export.folder_label')} {output_dir}",
            )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.btn_export.setEnabled(True)
            self.btn_export.setText(_t("common.export"))
            logger.exception("Export failed: %s", e)
            QMessageBox.critical(
                self, _t("data_export.failed_title"), _t("data_export.failed_msg", error=translate_error(str(e)))
            )

    def _write_export(self, svc: object, df, filepath: str, title: str, fmt: str) -> None:
        """Write a DataFrame to the specified format."""
        if fmt == "excel":
            svc.export_to_excel(df, filepath, title)
        elif fmt == "csv":
            svc.export_to_csv(df, filepath)
        elif fmt == "pdf":
            svc.export_to_pdf(df, filepath, title)
