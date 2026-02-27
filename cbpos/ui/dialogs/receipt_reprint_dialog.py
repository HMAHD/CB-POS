import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QDateEdit,
    QMessageBox,
)
from PyQt6.QtCore import QDate
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)


class ReceiptReprintDialog(QDialog):
    """Dialog to search past sales and reprint receipts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reprint Receipt")
        self.setMinimumSize(700, 500)
        self.setObjectName("ReceiptReprintDialog")
        self.results = []
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Search bar
        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by receipt number...")
        self.search_input.returnPressed.connect(self.perform_search)
        search_layout.addWidget(self.search_input, 2)

        lbl_from = QLabel("From:")
        lbl_from.setStyleSheet("background: transparent;")
        search_layout.addWidget(lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-7))
        search_layout.addWidget(self.date_from)

        lbl_to = QLabel("To:")
        lbl_to.setStyleSheet("background: transparent;")
        search_layout.addWidget(lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        search_layout.addWidget(self.date_to)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet("background-color: #00BCEB; color: black; font-weight: bold; padding: 8px 16px;")
        btn_search.clicked.connect(self.perform_search)
        search_layout.addWidget(btn_search)

        layout.addLayout(search_layout)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["ID", "Receipt #", "Date", "Customer", "Total"])
        self.results_table.setColumnHidden(0, True)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.doubleClicked.connect(self.reprint_selected)
        layout.addWidget(self.results_table)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_reprint = QPushButton("Reprint")
        btn_reprint.setStyleSheet("background-color: #39FF14; color: black; font-weight: bold; padding: 10px 24px;")
        btn_reprint.clicked.connect(self.reprint_selected)
        btn_layout.addWidget(btn_reprint)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("padding: 10px 24px;")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def perform_search(self) -> None:
        """Search for past sales by doc number or date range."""
        search_term = self.search_input.text().strip() or None
        d_from = self.date_from.date()
        d_to = self.date_to.date()

        from_dt = datetime(d_from.year(), d_from.month(), d_from.day())
        to_dt = datetime(d_to.year(), d_to.month(), d_to.day(), 23, 59, 59)

        try:
            self.results = TransactionService.get_sales_history(
                from_date=from_dt,
                to_date=to_dt,
                search_term=search_term,
                limit=100,
            )
            self._populate_table()
        except Exception as e:
            logger.error(f"Receipt search failed: {e}")
            QMessageBox.critical(self, "Error", f"Search failed: {e}")

    def _populate_table(self) -> None:
        """Fill results table with sales data."""
        self.results_table.setRowCount(0)
        for sale in self.results:
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)

            self.results_table.setItem(row, 0, QTableWidgetItem(str(sale.id)))
            self.results_table.setItem(row, 1, QTableWidgetItem(sale.document_number or f"#{sale.id}"))

            date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
            self.results_table.setItem(row, 2, QTableWidgetItem(date_str))

            customer_name = sale.customer.name if sale.customer else "Walk-in"
            self.results_table.setItem(row, 3, QTableWidgetItem(customer_name))

            self.results_table.setItem(row, 4, QTableWidgetItem(format_currency(sale.total_amount)))

    def reprint_selected(self) -> None:
        """Reprint receipt for the selected sale."""
        row = self.results_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a sale to reprint.")
            return

        sale = self.results[row]

        try:
            commands = ReceiptBuilder.build_receipt(sale)
            worker = PrintWorker()
            worker.add_job("print_receipt", commands)
            QMessageBox.information(self, "Reprinting", f"Sending receipt {sale.document_number} to printer...")
        except Exception as e:
            logger.error(f"Reprint failed: {e}")
            QMessageBox.critical(self, "Error", f"Reprint failed: {e}")
