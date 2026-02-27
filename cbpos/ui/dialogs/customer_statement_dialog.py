"""
Dialog for viewing and printing customer account statements.
"""

import logging
from datetime import datetime
from decimal import Decimal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QDate
from cbpos.core.services.statement_service import StatementService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)


class CustomerStatementDialog(QDialog):
    """Dialog to view and print a customer account statement."""

    def __init__(self, customer, parent=None):
        super().__init__(parent)
        self.customer = customer
        self.statement_data = None

        self.setWindowTitle(f"Statement — {customer.name}")
        self.setMinimumSize(750, 550)
        self.setObjectName("CustomerStatementDialog")
        self._init_ui()
        self._load_statement()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Customer header
        header_layout = QHBoxLayout()
        self.lbl_customer = QLabel(f"{self.customer.name}")
        self.lbl_customer.setStyleSheet("font-size: 16px; font-weight: bold; background: transparent;")
        header_layout.addWidget(self.lbl_customer)

        if self.customer.phone:
            lbl_phone = QLabel(f"Phone: {self.customer.phone}")
            lbl_phone.setStyleSheet("color: #aaa; background: transparent;")
            header_layout.addWidget(lbl_phone)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Date filter
        filter_layout = QHBoxLayout()
        lbl_from = QLabel("From:")
        lbl_from.setStyleSheet("background: transparent;")
        filter_layout.addWidget(lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.date_from)

        lbl_to = QLabel("To:")
        lbl_to.setStyleSheet("background: transparent;")
        filter_layout.addWidget(lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.date_to)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet("background-color: #00BCEB; color: black; font-weight: bold; padding: 6px 14px;")
        btn_refresh.clicked.connect(self._load_statement)
        filter_layout.addWidget(btn_refresh)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Summary labels
        summary_layout = QHBoxLayout()
        self.lbl_opening = QLabel("Opening: ---")
        self.lbl_opening.setStyleSheet("background: transparent;")
        self.lbl_total_debit = QLabel("Sales: ---")
        self.lbl_total_debit.setStyleSheet("font-weight: bold; color: #FF4136; background: transparent;")
        self.lbl_total_credit = QLabel("Payments: ---")
        self.lbl_total_credit.setStyleSheet("font-weight: bold; color: #39FF14; background: transparent;")
        self.lbl_closing = QLabel("Closing: ---")
        self.lbl_closing.setStyleSheet("font-weight: bold; background: transparent;")
        summary_layout.addWidget(self.lbl_opening)
        summary_layout.addWidget(self.lbl_total_debit)
        summary_layout.addWidget(self.lbl_total_credit)
        summary_layout.addStretch()
        summary_layout.addWidget(self.lbl_closing)
        layout.addLayout(summary_layout)

        # Entries table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Date", "Type", "Description", "Debit", "Credit", "Balance"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_print = QPushButton("Print Statement")
        btn_print.setStyleSheet("background-color: #0074D9; color: white; font-weight: bold; padding: 10px 20px;")
        btn_print.clicked.connect(self._print_thermal)
        btn_layout.addWidget(btn_print)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("padding: 10px 20px;")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _get_date_range(self) -> tuple:
        d_from = self.date_from.date()
        d_to = self.date_to.date()
        return (
            datetime(d_from.year(), d_from.month(), d_from.day()),
            datetime(d_to.year(), d_to.month(), d_to.day(), 23, 59, 59),
        )

    def _load_statement(self) -> None:
        """Load statement data and populate the table."""
        from_dt, to_dt = self._get_date_range()

        try:
            self.statement_data = StatementService.generate_statement(
                customer_id=self.customer.id,
                date_from=from_dt,
                date_to=to_dt,
            )
        except Exception as e:
            logger.error(f"Failed to load statement: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load statement: {e}")
            return

        data = self.statement_data

        # Update summaries
        self.lbl_opening.setText(f"Opening: {format_currency(data['opening_balance'])}")
        self.lbl_total_debit.setText(f"Sales: {format_currency(data['total_debit'])}")
        self.lbl_total_credit.setText(f"Payments: {format_currency(data['total_credit'])}")
        self.lbl_closing.setText(f"Closing: {format_currency(data['closing_balance'])}")

        # Populate table
        self.table.setRowCount(0)
        for entry in data["entries"]:
            row = self.table.rowCount()
            self.table.insertRow(row)

            date_str = entry["date"].strftime("%Y-%m-%d") if entry["date"] else ""
            self.table.setItem(row, 0, QTableWidgetItem(date_str))
            self.table.setItem(row, 1, QTableWidgetItem(entry["type"]))
            self.table.setItem(row, 2, QTableWidgetItem(entry["description"]))

            debit_str = format_currency(entry["debit"]) if entry["debit"] > 0 else ""
            credit_str = format_currency(entry["credit"]) if entry["credit"] > 0 else ""
            self.table.setItem(row, 3, QTableWidgetItem(debit_str))
            self.table.setItem(row, 4, QTableWidgetItem(credit_str))
            self.table.setItem(row, 5, QTableWidgetItem(format_currency(entry["balance"])))

    def _print_thermal(self) -> None:
        """Print statement on thermal printer."""
        from_dt, to_dt = self._get_date_range()

        entries = CustomerCreditService.get_ledger(
            self.customer.id,
            date_from=from_dt,
            date_to=to_dt,
        )

        commands = ReceiptBuilder.build_customer_statement(
            customer=self.customer,
            entries=entries,
            period_from=from_dt,
            period_to=to_dt,
        )

        worker = PrintWorker()
        worker.add_job("print_commands", commands)
        QMessageBox.information(self, "Print", "Statement sent to printer.")
