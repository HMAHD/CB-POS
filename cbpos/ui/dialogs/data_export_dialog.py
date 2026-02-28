"""
Data Export dialog for CB-POS.

Allows users to select which data to export (Products, Customers, Sales),
choose a format (CSV, Excel, PDF), pick a date range for sales,
and export to a chosen directory.
"""

import logging
from datetime import datetime

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

logger = logging.getLogger(__name__)

_BTN_PRIMARY = """
    QPushButton {
        background-color: #00BCEB;
        color: #001F3F;
        border: none;
        border-radius: 6px;
        padding: 10px 24px;
        font-weight: bold;
        font-size: 13px;
    }
    QPushButton:hover { background-color: #33CCFF; }
    QPushButton:pressed { background-color: #0099CC; }
    QPushButton:disabled { background-color: #555555; color: #999999; }
"""

_BTN_SECONDARY = """
    QPushButton {
        background-color: transparent;
        color: #00BCEB;
        border: 1px solid #00BCEB;
        border-radius: 6px;
        padding: 10px 24px;
        font-size: 13px;
    }
    QPushButton:hover { background-color: rgba(0, 188, 235, 0.15); }
    QPushButton:disabled { border-color: #555555; color: #555555; }
"""

_CARD_STYLE = """
    QGroupBox {
        background-color: #003366;
        border: 1px solid #004080;
        border-radius: 8px;
        margin-top: 16px;
        padding: 20px 16px 16px 16px;
        font-weight: bold;
        color: #00BCEB;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 8px;
    }
"""

_INPUT_STYLE = """
    QDateEdit, QComboBox {
        background-color: #002244;
        border: 1px solid #004080;
        border-radius: 6px;
        padding: 8px 12px;
        color: #E0E0E0;
        font-size: 13px;
    }
    QDateEdit:focus, QComboBox:focus { border-color: #00BCEB; }
    QComboBox::drop-down {
        border: none;
        padding-right: 8px;
    }
    QComboBox QAbstractItemView {
        background-color: #002244;
        color: #E0E0E0;
        selection-background-color: #004080;
    }
"""

_CHK_STYLE = """
    QCheckBox {
        color: #E0E0E0;
        font-size: 13px;
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 20px;
        height: 20px;
        border-radius: 4px;
        border: 2px solid #004080;
        background-color: #002244;
    }
    QCheckBox::indicator:checked {
        background-color: #00BCEB;
        border-color: #00BCEB;
    }
"""


class DataExportDialog(QDialog):
    """Dialog for exporting Products, Customers, and Sales data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self.setMinimumSize(520, 480)
        self.resize(560, 500)
        self.setStyleSheet("QDialog { background-color: #001F3F; }")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Export Business Data")
        title.setStyleSheet("color: #00BCEB; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel("Select which data to export and the output format.")
        desc.setStyleSheet("color: #8899AA; font-size: 12px; margin-bottom: 8px;")
        layout.addWidget(desc)

        # Data selection
        grp_data = QGroupBox("Select Data")
        grp_data.setStyleSheet(_CARD_STYLE)
        data_layout = QVBoxLayout(grp_data)
        data_layout.setSpacing(10)

        self.chk_products = QCheckBox("Products")
        self.chk_products.setChecked(True)
        self.chk_products.setStyleSheet(_CHK_STYLE)
        data_layout.addWidget(self.chk_products)

        self.chk_customers = QCheckBox("Customers")
        self.chk_customers.setStyleSheet(_CHK_STYLE)
        data_layout.addWidget(self.chk_customers)

        self.chk_sales = QCheckBox("Sales")
        self.chk_sales.setChecked(True)
        self.chk_sales.setStyleSheet(_CHK_STYLE)
        self.chk_sales.toggled.connect(self._toggle_date_range)
        data_layout.addWidget(self.chk_sales)

        layout.addWidget(grp_data)

        # Date range for sales
        self.grp_dates = QGroupBox("Sales Date Range")
        self.grp_dates.setStyleSheet(_CARD_STYLE + _INPUT_STYLE)
        dates_form = QFormLayout(self.grp_dates)
        dates_form.setVerticalSpacing(10)
        dates_form.setHorizontalSpacing(16)

        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addMonths(-1))
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        dates_form.addRow(self._label("From:"), self.date_start)

        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        dates_form.addRow(self._label("To:"), self.date_end)

        layout.addWidget(self.grp_dates)

        # Format selector
        grp_format = QGroupBox("Output Format")
        grp_format.setStyleSheet(_CARD_STYLE + _INPUT_STYLE)
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
        btn_cancel.setStyleSheet(_BTN_SECONDARY)
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_layout.addStretch()

        self.btn_export = QPushButton("Export")
        self.btn_export.setStyleSheet(_BTN_PRIMARY)
        self.btn_export.setFixedWidth(140)
        self.btn_export.clicked.connect(self._do_export)
        btn_layout.addWidget(self.btn_export)

        layout.addLayout(btn_layout)

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #B0B0B0; font-size: 12px;")
        return lbl

    def _toggle_date_range(self, checked: bool) -> None:
        self.grp_dates.setVisible(checked)

    def _do_export(self) -> None:
        if not any([self.chk_products.isChecked(), self.chk_customers.isChecked(), self.chk_sales.isChecked()]):
            QMessageBox.warning(self, "No Data Selected", "Please select at least one data type to export.")
            return

        # Ask for output directory
        from pathlib import Path

        default_dir = str(Path.home() / "Documents")
        output_dir = QFileDialog.getExistingDirectory(self, "Choose Export Folder", default_dir)
        if not output_dir:
            return

        self.btn_export.setEnabled(False)
        self.btn_export.setText("Exporting...")
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        try:
            from cbpos.core.services.data_export_service import DataExportService
            from cbpos.core.services.export_service import ExportService

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
            QMessageBox.critical(self, "Export Failed", f"Could not export data:\n{e}")

    def _write_export(self, svc: object, df, filepath: str, title: str, fmt: str) -> None:
        """Write a DataFrame to the specified format."""
        if fmt == "excel":
            svc.export_to_excel(df, filepath, title)
        elif fmt == "csv":
            svc.export_to_csv(df, filepath)
        elif fmt == "pdf":
            svc.export_to_pdf(df, filepath, title)
