from datetime import date
from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QInputDialog,
    QFrame,
    QGridLayout,
)

from cbpos.core.services.report_service import ReportService
from cbpos.core.services.shift_service import ShiftService


class ReportsView(QWidget):
    def __init__(self):
        super().__init__()
        self.report_service = ReportService()
        self.shift_service = ShiftService()
        # TODO: Get actual logged in user ID
        self.current_user_id = 1

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()

        # Tab 1: Dashboard
        self.tab_dashboard = QWidget()
        self.setup_dashboard_tab()
        self.tabs.addTab(self.tab_dashboard, "Dashboard")

        # Tab 2: Sales Report
        self.tab_sales = QWidget()
        self.setup_sales_tab()
        self.tabs.addTab(self.tab_sales, "Sales Report")

        # Tab 3: Z-Report (Shift Management)
        self.tab_z_report = QWidget()
        self.setup_z_report_tab()
        self.tabs.addTab(self.tab_z_report, "Shift / Z-Report")

        layout.addWidget(self.tabs)

    def setup_dashboard_tab(self):
        layout = QVBoxLayout(self.tab_dashboard)

        # Tiles Area
        tiles_layout = QGridLayout()

        self.tile_sales = self.create_tile("Total Sales Today", "0.00")
        self.tile_txns = self.create_tile("Transactions", "0")
        self.tile_shift = self.create_tile("Current Shift", "CLOSED")

        tiles_layout.addWidget(self.tile_sales, 0, 0)
        tiles_layout.addWidget(self.tile_txns, 0, 1)
        tiles_layout.addWidget(self.tile_shift, 0, 2)

        layout.addLayout(tiles_layout)

        # Refresh Button
        refresh_btn = QPushButton("Refresh Dashboard")
        refresh_btn.clicked.connect(self.refresh_dashboard)
        layout.addWidget(refresh_btn)

        layout.addStretch()

    def create_tile(self, title, value):
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "background-color: #001F3F; color: white; border-radius: 10px;"
        )

        layout = QVBoxLayout(frame)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 14px; color: #AAAAAA;")
        lbl_value = QLabel(value)
        lbl_value.setStyleSheet("font-size: 24px; font-weight: bold; color: #00BCEB;")

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_value)
        return frame

    def setup_sales_tab(self):
        layout = QVBoxLayout(self.tab_sales)

        # Controls
        controls = QHBoxLayout()
        self.date_picker = QDateEdit()
        self.date_picker.setDate(date.today())
        self.date_picker.setCalendarPopup(True)

        btn_load = QPushButton("Load Report")
        btn_load.clicked.connect(self.load_sales_report)

        controls.addWidget(QLabel("Date:"))
        controls.addWidget(self.date_picker)
        controls.addWidget(btn_load)
        controls.addStretch()

        layout.addLayout(controls)

        # Results Area
        self.lbl_total_sales = QLabel("Total Sales: 0.00")
        self.lbl_total_tax = QLabel("Total Tax: 0.00")
        layout.addWidget(self.lbl_total_sales)
        layout.addWidget(self.lbl_total_tax)

        # Breakdown Table
        self.sales_table = QTableWidget()
        self.sales_table.setColumnCount(2)
        self.sales_table.setHorizontalHeaderLabels(["Payment Method", "Amount"])
        self.sales_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.sales_table)

    def setup_z_report_tab(self):
        layout = QVBoxLayout(self.tab_z_report)

        self.lbl_shift_status = QLabel("Shift Status: CHECKING...")
        self.btn_start_shift = QPushButton("Start Shift")
        self.btn_close_shift = QPushButton("Close Shift (Z-Read)")

        self.btn_start_shift.clicked.connect(self.start_shift)
        self.btn_close_shift.clicked.connect(self.close_shift)

        layout.addWidget(self.lbl_shift_status)
        layout.addWidget(self.btn_start_shift)
        layout.addWidget(self.btn_close_shift)

        layout.addStretch()

        # Initial check
        self.check_shift_status()

    def refresh_dashboard(self):
        today = date.today()
        data = self.report_service.get_daily_sales(today)

        # Update Tiles (Accessing labels inside frames is a bit hacky, normally keep ref)
        # For simplicity, just rebuilding or assuming structure
        self.tile_sales.findChild(QLabel, "").nextInFocusChain().setText(
            "{:.2f}".format(data["total_sales"])
        )

        # Check shift
        shift = self.shift_service.get_current_shift(self.current_user_id)
        status = "OPEN" if shift else "CLOSED"
        self.tile_shift.findChild(QLabel, "").nextInFocusChain().setText(status)

    def load_sales_report(self):
        selected_date = self.date_picker.date().toPyDate()
        data = self.report_service.get_daily_sales(selected_date)

        self.lbl_total_sales.setText("Total Sales: {:.2f}".format(data["total_sales"]))
        self.lbl_total_tax.setText("Total Tax: {:.2f}".format(data["total_tax"]))

        self.sales_table.setRowCount(0)
        for method, amount in data["payment_breakdown"].items():
            row = self.sales_table.rowCount()
            self.sales_table.insertRow(row)
            self.sales_table.setItem(row, 0, QTableWidgetItem(method))
            self.sales_table.setItem(row, 1, QTableWidgetItem("{:.2f}".format(amount)))

    def check_shift_status(self):
        shift = self.shift_service.get_current_shift(self.current_user_id)
        if shift:
            self.lbl_shift_status.setText(f"Shift OPEN (Started: {shift.start_time})")
            self.btn_start_shift.setEnabled(False)
            self.btn_close_shift.setEnabled(True)
        else:
            self.lbl_shift_status.setText("Shift CLOSED")
            self.btn_start_shift.setEnabled(True)
            self.btn_close_shift.setEnabled(False)

    def start_shift(self):
        amount, ok = QInputDialog.getDouble(
            self, "Start Shift", "Enter Opening Float:", 0, 0, 100000, 2
        )
        if ok:
            try:
                self.shift_service.start_shift(
                    self.current_user_id, Decimal(str(amount))
                )
                self.check_shift_status()
                QMessageBox.information(self, "Success", "Shift Started")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def close_shift(self):
        shift = self.shift_service.get_current_shift(self.current_user_id)
        if not shift:
            return

        amount, ok = QInputDialog.getDouble(
            self, "Close Shift", "Enter Counted Cash:", 0, 0, 1000000, 2
        )
        if ok:
            try:
                result = self.shift_service.close_shift(shift.id, Decimal(str(amount)))

                msg = (
                    "Shift Closed Successfully\n\n"
                    "Expected Cash: {:.2f}\n"
                    "Actual Cash: {:.2f}\n"
                    "Variance: {:.2f}\n\n"
                    "Total Sales: {:.2f}".format(
                        result["expected_cash"],
                        result["actual_cash"],
                        result["variance"],
                        result["cash_sales"],
                    )
                )
                QMessageBox.information(self, "Z-Report", msg)
                self.check_shift_status()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
