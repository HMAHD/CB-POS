"""
Dialog for viewing and printing customer account statements.
"""

import logging
from datetime import datetime
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
from PyQt6.QtCore import QDate
from cbpos.core.services.statement_service import StatementService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class CustomerStatementDialog(QDialog):
    """Dialog to view and print a customer account statement."""

    def __init__(self, customer, parent=None):
        super().__init__(parent)
        self.customer = customer
        self.statement_data = None

        self.setWindowTitle(_t("customer_statement.title", name=customer.name))
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
        self.lbl_customer.setProperty("class", "dialog-title")
        header_layout.addWidget(self.lbl_customer)

        if self.customer.phone:
            lbl_phone = QLabel(_t("customer_statement.phone", phone=self.customer.phone))
            lbl_phone.setProperty("class", "muted")
            header_layout.addWidget(lbl_phone)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Date filter
        filter_layout = QHBoxLayout()
        lbl_from = QLabel(_t("common.from"))
        lbl_from.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.date_from)

        lbl_to = QLabel(_t("common.to"))
        lbl_to.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.date_to)

        btn_refresh = QPushButton(_t("common.refresh"))
        btn_refresh.setProperty("class", "accent")
        btn_refresh.clicked.connect(self._load_statement)
        filter_layout.addWidget(btn_refresh)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Summary labels
        summary_layout = QHBoxLayout()
        self.lbl_opening = QLabel(_t("customer_statement.opening", value="---"))
        self.lbl_opening.setProperty("class", "transparent")
        self.lbl_total_debit = QLabel(_t("customer_statement.sales", value="---"))
        self.lbl_total_debit.setProperty("class", "debit")
        self.lbl_total_credit = QLabel(_t("customer_statement.payments", value="---"))
        self.lbl_total_credit.setProperty("class", "credit")
        self.lbl_closing = QLabel(_t("customer_statement.closing", value="---"))
        self.lbl_closing.setProperty("class", "bold")
        summary_layout.addWidget(self.lbl_opening)
        summary_layout.addWidget(self.lbl_total_debit)
        summary_layout.addWidget(self.lbl_total_credit)
        summary_layout.addStretch()
        summary_layout.addWidget(self.lbl_closing)
        layout.addLayout(summary_layout)

        # Entries table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                _t("customer_statement.col_date"),
                _t("customer_statement.col_type"),
                _t("customer_statement.col_description"),
                _t("customer_statement.col_debit"),
                _t("customer_statement.col_credit"),
                _t("customer_statement.col_balance"),
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_print = QPushButton(_t("customer_statement.print_statement"))
        btn_print.setProperty("class", "accent")
        btn_print.clicked.connect(self._print_thermal)
        btn_layout.addWidget(btn_print)

        btn_close = QPushButton(_t("common.close"))
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
            QMessageBox.critical(self, _t("common.error"), _t("customer_statement.load_failed", error=str(e)))
            return

        data = self.statement_data

        # Update summaries
        self.lbl_opening.setText(_t("customer_statement.opening", value=format_currency(data["opening_balance"])))
        self.lbl_total_debit.setText(_t("customer_statement.sales", value=format_currency(data["total_debit"])))
        self.lbl_total_credit.setText(_t("customer_statement.payments", value=format_currency(data["total_credit"])))
        self.lbl_closing.setText(_t("customer_statement.closing", value=format_currency(data["closing_balance"])))

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

        worker = PrintWorker.instance()
        worker.add_job("print_commands", commands)
        QMessageBox.information(self, _t("common.print"), _t("customer_statement.print_sent"))
