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

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QDateEdit,
    QMessageBox,
    QApplication,
    QFormLayout,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QCursor

from cbpos.core.services.data_export_service import DataExportService
from cbpos.core.services.export_service import ExportService

logger = logging.getLogger(__name__)


class DataExportDialog(QDialog):
    """Dialog for exporting Products, Customers, and Sales data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self.setMinimumSize(520, 480)
        self.resize(560, 500)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Export Business Data")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        desc = QLabel("Select which data to export and the output format.")
        desc.setProperty("class", "muted")
        layout.addWidget(desc)

        # Data selection
        grp_data = QGroupBox("Select Data")
        data_layout = QVBoxLayout(grp_data)
        data_layout.setSpacing(10)

        self.chk_products = QCheckBox("Products")
        self.chk_products.setChecked(True)
        data_layout.addWidget(self.chk_products)

        self.chk_customers = QCheckBox("Customers")
        data_layout.addWidget(self.chk_customers)

        self.chk_sales = QCheckBox("Sales")
        self.chk_sales.setChecked(True)
        self.chk_sales.toggled.connect(self._toggle_date_range)
        data_layout.addWidget(self.chk_sales)

        layout.addWidget(grp_data)

        # Date range for sales
        self.grp_dates = QGroupBox("Sales Date Range")
        dates_form = QFormLayout(self.grp_dates)
        dates_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        dates_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        dates_form.setVerticalSpacing(10)
        dates_form.setHorizontalSpacing(16)

        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addMonths(-1))
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        dates_form.addRow("From:", self.date_start)

        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        dates_form.addRow("To:", self.date_end)

        layout.addWidget(self.grp_dates)

        # Format selector
        grp_format = QGroupBox("Output Format")
        fmt_layout = QHBoxLayout(grp_format)

        self.cmb_format = QComboBox()
        self.cmb_format.addItems(["Excel (.xlsx)", "CSV (.csv)", "PDF (.pdf)"])
        self.cmb_format.setFixedWidth(200)
        fmt_layout.addWidget(self.cmb_format)
        fmt_layout.addStretch()

        layout.addWidget(grp_format)
        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_layout.addStretch()

        self.btn_export = QPushButton("Export")
        self.btn_export.setProperty("class", "accent")
        self.btn_export.setFixedWidth(140)
        self.btn_export.clicked.connect(self._do_export)
        btn_layout.addWidget(self.btn_export)

        layout.addLayout(btn_layout)

    def _toggle_date_range(self, checked: bool) -> None:
        self.grp_dates.setVisible(checked)

    def _do_export(self) -> None:
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.REPORTS_EXPORT, self):
            return

        if not any([self.chk_products.isChecked(), self.chk_customers.isChecked(), self.chk_sales.isChecked()]):
            QMessageBox.warning(self, "No Data Selected", "Please select at least one data type to export.")
            return

        # Ask for output directory
        default_dir = str(Path.home() / "Documents")
        output_dir = QFileDialog.getExistingDirectory(self, "Choose Export Folder", default_dir)
        if not output_dir:
            return

        self.btn_export.setEnabled(False)
        self.btn_export.setText("Exporting...")
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        try:
            export_svc = ExportService()
            fmt_text = self.cmb_format.currentText()

            if "Excel" in fmt_text:
                ext = ".xlsx"
                fmt = "excel"
            elif "CSV" in fmt_text:
                ext = ".csv"
                fmt = "csv"
            else:
                ext = ".pdf"
                fmt = "pdf"

            exported = []
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if self.chk_products.isChecked():
                df = DataExportService.get_products_dataframe()
                filepath = f"{output_dir}/products_{timestamp}{ext}"
                self._write_export(export_svc, df, filepath, "Products", fmt)
                exported.append(f"Products ({len(df)} rows)")

            if self.chk_customers.isChecked():
                df = DataExportService.get_customers_dataframe()
                filepath = f"{output_dir}/customers_{timestamp}{ext}"
                self._write_export(export_svc, df, filepath, "Customers", fmt)
                exported.append(f"Customers ({len(df)} rows)")

            if self.chk_sales.isChecked():
                start = self.date_start.date().toPyDate()
                end = self.date_end.date().toPyDate()
                start_dt = datetime(start.year, start.month, start.day, 0, 0, 0)
                end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)
                df = DataExportService.get_sales_dataframe(start_dt, end_dt)
                filepath = f"{output_dir}/sales_{timestamp}{ext}"
                self._write_export(export_svc, df, filepath, "Sales", fmt)
                exported.append(f"Sales ({len(df)} rows)")

            QApplication.restoreOverrideCursor()
            self.btn_export.setEnabled(True)
            self.btn_export.setText("Export")

            QMessageBox.information(
                self,
                "Export Complete",
                "Exported successfully:\n\n" + "\n".join(f"  {e}" for e in exported) + f"\n\nFolder: {output_dir}",
            )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.btn_export.setEnabled(True)
            self.btn_export.setText("Export")
            logger.exception("Export failed: %s", e)
            QMessageBox.critical(self, "Export Failed", f"Could not export data:\n{e}")  # noqa: E231

    def _write_export(self, svc: object, df, filepath: str, title: str, fmt: str) -> None:
        """Write a DataFrame to the specified format."""
        if fmt == "excel":
            svc.export_to_excel(df, filepath, title)
        elif fmt == "csv":
            svc.export_to_csv(df, filepath)
        elif fmt == "pdf":
            svc.export_to_pdf(df, filepath, title)
