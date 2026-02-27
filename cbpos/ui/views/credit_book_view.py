import logging
from decimal import Decimal
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
    QLabel,
    QPushButton,
    QFrame,
    QDateEdit,
    QMessageBox,
    QInputDialog,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.utils.formatters import format_currency
from cbpos.ui.dialogs.customer_editor import CustomerEditor

logger = logging.getLogger(__name__)


class CreditBookView(QWidget):
    """
    Two-panel Credit Book view.
    Left: customer list with debt indicators.
    Right: selected customer's ledger and actions.
    """

    def __init__(self) -> None:
        super().__init__()
        self.customer_service = CustomerService()
        self.selected_customer = None
        self.init_ui()
        self.load_customers()

    def init_ui(self) -> None:
        self.setObjectName("CreditBookView")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)

        # ========== LEFT PANEL: Customer List ==========
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 5, 10)

        # Title
        lbl_title = QLabel("Credit Book")
        lbl_title.setProperty("class", "dialog-title")
        left_layout.addWidget(lbl_title)

        # Search
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or phone...")
        self.search_input.textChanged.connect(self.filter_customers)
        search_layout.addWidget(self.search_input)

        self.btn_add_customer = QPushButton("+ Add")
        self.btn_add_customer.setProperty("class", "accent")
        self.btn_add_customer.clicked.connect(self.open_add_customer)
        search_layout.addWidget(self.btn_add_customer)
        left_layout.addLayout(search_layout)

        # Customer Table
        self.customer_table = QTableWidget()
        self.customer_table.setColumnCount(5)
        self.customer_table.setHorizontalHeaderLabels(["ID", "Name", "Phone", "Debt", "Limit"])
        self.customer_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.customer_table.setColumnHidden(0, True)  # Hide ID column
        self.customer_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.customer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.customer_table.currentItemChanged.connect(self.on_customer_selected)
        self.customer_table.setAlternatingRowColors(True)
        self.customer_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.customer_table, 1)  # stretch to fill

        splitter.addWidget(left_panel)

        # ========== RIGHT PANEL: Ledger & Actions ==========
        right_panel = QWidget()
        self.right_layout = QVBoxLayout(right_panel)
        self.right_layout.setContentsMargins(5, 10, 10, 10)

        # Customer Header Card
        self.header_card = QFrame()
        self.header_card.setObjectName("CreditHeaderCard")
        header_layout = QVBoxLayout(self.header_card)

        # Row 1: Name + Phone
        row1 = QHBoxLayout()
        self.lbl_cust_name = QLabel("Select a customer")
        self.lbl_cust_name.setProperty("class", "bold")
        self.lbl_cust_phone = QLabel("")
        self.lbl_cust_phone.setProperty("class", "muted")
        row1.addWidget(self.lbl_cust_name)
        row1.addStretch()
        row1.addWidget(self.lbl_cust_phone)
        header_layout.addLayout(row1)

        # Row 2: Debt, Limit, Available, Last Payment
        row2 = QHBoxLayout()
        self.lbl_debt = QLabel("Debt: ---")
        self.lbl_debt.setProperty("class", "debit")
        self.lbl_available = QLabel("Available: ---")
        self.lbl_available.setProperty("class", "credit")
        self.lbl_last_payment = QLabel("Last Payment: ---")
        self.lbl_last_payment.setProperty("class", "muted")
        row2.addWidget(self.lbl_debt)
        row2.addWidget(self.lbl_available)
        row2.addStretch()
        row2.addWidget(self.lbl_last_payment)
        header_layout.addLayout(row2)

        self.right_layout.addWidget(self.header_card)

        # Action Buttons
        action_layout = QHBoxLayout()

        self.btn_receive_payment = QPushButton("Receive Payment")
        self.btn_receive_payment.setProperty("class", "primary")
        self.btn_receive_payment.clicked.connect(self.receive_payment)
        action_layout.addWidget(self.btn_receive_payment)

        self.btn_print_statement = QPushButton("Print Statement")
        self.btn_print_statement.setProperty("class", "accent")
        self.btn_print_statement.clicked.connect(self.print_statement)
        action_layout.addWidget(self.btn_print_statement)

        self.btn_adjust = QPushButton("Adjust Balance")
        self.btn_adjust.setProperty("class", "warning")
        self.btn_adjust.clicked.connect(self.adjust_balance)
        action_layout.addWidget(self.btn_adjust)

        self.btn_edit_customer = QPushButton("Edit Customer")
        self.btn_edit_customer.clicked.connect(self.edit_customer)
        action_layout.addWidget(self.btn_edit_customer)

        self.right_layout.addLayout(action_layout)

        # Date Filters
        filter_layout = QHBoxLayout()
        lbl_from = QLabel("From:")
        lbl_from.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_from.dateChanged.connect(self.reload_ledger)
        filter_layout.addWidget(self.date_from)

        lbl_to = QLabel("To:")
        lbl_to.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self.reload_ledger)
        filter_layout.addWidget(self.date_to)

        self.btn_all_dates = QPushButton("All")
        self.btn_all_dates.clicked.connect(self.show_all_dates)
        filter_layout.addWidget(self.btn_all_dates)

        filter_layout.addStretch()
        self.right_layout.addLayout(filter_layout)

        # Ledger Table
        self.ledger_table = QTableWidget()
        self.ledger_table.setColumnCount(6)
        self.ledger_table.setHorizontalHeaderLabels(["Date", "Type", "Doc #", "Debit", "Credit", "Balance"])
        self.ledger_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.ledger_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ledger_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ledger_table.setAlternatingRowColors(True)
        self.ledger_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.right_layout.addWidget(self.ledger_table, 1)  # stretch to fill

        # Footer Summary
        footer_layout = QHBoxLayout()
        self.lbl_total_sales = QLabel("Sales: ---")
        self.lbl_total_sales.setProperty("class", "debit")
        self.lbl_total_payments = QLabel("Payments: ---")
        self.lbl_total_payments.setProperty("class", "credit")
        self.lbl_closing = QLabel("Closing: ---")
        self.lbl_closing.setProperty("class", "bold")
        footer_layout.addWidget(self.lbl_total_sales)
        footer_layout.addWidget(self.lbl_total_payments)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_closing)
        self.right_layout.addLayout(footer_layout)

        splitter.addWidget(right_panel)

        # Splitter proportions: 35% / 65%
        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 65)

        layout.addWidget(splitter)

    # ========== Customer List Methods ==========

    def load_customers(self) -> None:
        """Load all active customers into the table."""
        customers = self.customer_service.get_all_customers()
        self.populate_customer_table(customers)

    def filter_customers(self, text: str) -> None:
        """Filter customers by search text."""
        if not text:
            self.load_customers()
            return
        customers = self.customer_service.search_customers(text)
        self.populate_customer_table(customers)

    def populate_customer_table(self, customers: list) -> None:
        """Populate the customer table with color-coded debt status."""
        self.customer_table.setRowCount(0)
        for customer in customers:
            row = self.customer_table.rowCount()
            self.customer_table.insertRow(row)

            self.customer_table.setItem(row, 0, QTableWidgetItem(str(customer.id)))
            self.customer_table.setItem(row, 1, QTableWidgetItem(customer.name))
            self.customer_table.setItem(row, 2, QTableWidgetItem(customer.phone or ""))

            # Debt with color coding
            debt_item = QTableWidgetItem(f"{customer.current_debt:.2f}")  # noqa: E231
            debt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            limit_item = QTableWidgetItem(f"{customer.credit_limit:.2f}")  # noqa: E231
            limit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            if customer.credit_limit > 0:
                ratio = customer.current_debt / customer.credit_limit
                if ratio >= Decimal("0.9"):
                    debt_item.setForeground(QColor("#FF4136"))  # Red
                elif ratio >= Decimal("0.5"):
                    debt_item.setForeground(QColor("#FF851B"))  # Orange
                elif customer.current_debt == 0:
                    debt_item.setForeground(QColor("#39FF14"))  # Green
            elif customer.current_debt > 0:
                debt_item.setForeground(QColor("#FF4136"))  # Red (no limit but has debt)

            self.customer_table.setItem(row, 3, debt_item)
            self.customer_table.setItem(row, 4, limit_item)

    def on_customer_selected(self, current: QTableWidgetItem, previous: QTableWidgetItem) -> None:
        """Handle customer selection from the table."""
        if not current:
            return

        row = current.row()
        customer_id_item = self.customer_table.item(row, 0)
        if not customer_id_item:
            return

        customer_id = int(customer_id_item.text())
        customer = self.customer_service.get_customer(customer_id)
        if customer:
            self.selected_customer = customer
            self.update_header(customer)
            self.reload_ledger()

    def update_header(self, customer) -> None:
        """Update the header card with customer details."""
        self.lbl_cust_name.setText(customer.name)
        self.lbl_cust_phone.setText(customer.phone or "No phone")

        summary = CustomerCreditService.get_customer_summary(customer.id)
        if summary:
            self.lbl_debt.setText(f"Debt: {format_currency(summary['current_debt'])}")
            self.lbl_available.setText(f"Available: {format_currency(summary['available'])}")
            if summary["last_payment_date"]:
                self.lbl_last_payment.setText(f"Last Payment: {summary['last_payment_date'].strftime('%Y-%m-%d')}")
            else:
                self.lbl_last_payment.setText("Last Payment: None")
        else:
            self.lbl_debt.setText("Debt: ---")
            self.lbl_available.setText("Available: ---")
            self.lbl_last_payment.setText("Last Payment: ---")

    # ========== Ledger Methods ==========

    def reload_ledger(self) -> None:
        """Reload ledger entries based on selected customer and date filters."""
        if not self.selected_customer:
            return

        date_from = datetime(
            self.date_from.date().year(),
            self.date_from.date().month(),
            self.date_from.date().day(),
        )
        date_to = datetime(
            self.date_to.date().year(),
            self.date_to.date().month(),
            self.date_to.date().day(),
            23,
            59,
            59,
        )

        entries = CustomerCreditService.get_ledger(
            self.selected_customer.id,
            date_from=date_from,
            date_to=date_to,
        )
        self.populate_ledger(entries)

    def show_all_dates(self) -> None:
        """Show all ledger entries (no date filter)."""
        if not self.selected_customer:
            return

        entries = CustomerCreditService.get_ledger(self.selected_customer.id)
        self.populate_ledger(entries)

    def populate_ledger(self, entries: list) -> None:
        """Populate the ledger table with entries."""
        self.ledger_table.setRowCount(0)

        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        closing_balance = Decimal("0.00")

        for entry in entries:
            row = self.ledger_table.rowCount()
            self.ledger_table.insertRow(row)

            # Date
            date_str = entry.timestamp.strftime("%Y-%m-%d %H:%M") if entry.timestamp else ""
            self.ledger_table.setItem(row, 0, QTableWidgetItem(date_str))

            # Type
            type_item = QTableWidgetItem(entry.entry_type)
            self.ledger_table.setItem(row, 1, type_item)

            # Doc #
            self.ledger_table.setItem(row, 2, QTableWidgetItem(entry.reference_doc or entry.note or ""))

            # Debit / Credit
            if entry.amount > 0:
                # Debit (sale increases debt)
                debit_item = QTableWidgetItem(f"{entry.amount:.2f}")  # noqa: E231
                debit_item.setForeground(QColor("#FF4136"))
                debit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.ledger_table.setItem(row, 3, debit_item)
                self.ledger_table.setItem(row, 4, QTableWidgetItem(""))
                total_debit += entry.amount
            else:
                # Credit (payment reduces debt)
                self.ledger_table.setItem(row, 3, QTableWidgetItem(""))
                credit_item = QTableWidgetItem(f"{abs(entry.amount):.2f}")  # noqa: E231
                credit_item.setForeground(QColor("#39FF14"))
                credit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.ledger_table.setItem(row, 4, credit_item)
                total_credit += abs(entry.amount)

            # Balance
            balance_item = QTableWidgetItem(f"{entry.balance_after:.2f}")  # noqa: E231
            balance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.ledger_table.setItem(row, 5, balance_item)

            closing_balance = entry.balance_after

        # Update footer
        self.lbl_total_sales.setText(f"Sales: {format_currency(total_debit)}")
        self.lbl_total_payments.setText(f"Payments: {format_currency(total_credit)}")
        self.lbl_closing.setText(f"Closing: {format_currency(closing_balance)}")

    # ========== Action Methods ==========

    def receive_payment(self) -> None:
        """Open the Receive Payment dialog for the selected customer."""
        if not self.selected_customer:
            QMessageBox.warning(self, "No Customer", "Please select a customer first.")
            return

        if self.selected_customer.current_debt <= 0:
            QMessageBox.information(self, "No Debt", "This customer has no outstanding debt.")
            return

        from cbpos.ui.dialogs.receive_payment_dialog import ReceivePaymentDialog

        dialog = ReceivePaymentDialog(self.selected_customer.id, self)
        if dialog.exec():
            # Refresh data
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)
            self.reload_ledger()
            self.load_customers()

    def print_statement(self) -> None:
        """Open customer statement dialog for viewing and printing."""
        if not self.selected_customer:
            QMessageBox.warning(self, "No Customer", "Please select a customer first.")
            return

        from cbpos.ui.dialogs.customer_statement_dialog import CustomerStatementDialog

        dialog = CustomerStatementDialog(self.selected_customer, self)
        dialog.exec()

    def adjust_balance(self) -> None:
        """Adjust the customer's balance (correction)."""
        if not self.selected_customer:
            QMessageBox.warning(self, "No Customer", "Please select a customer first.")
            return

        amount_str, ok = QInputDialog.getText(
            self,
            "Adjust Balance",
            "Enter adjustment amount (positive = increase debt, negative = decrease):",
        )
        if not ok or not amount_str:
            return

        try:
            amount = Decimal(amount_str)
        except Exception:
            QMessageBox.warning(self, "Invalid", "Invalid amount.")
            return

        note, ok = QInputDialog.getText(self, "Adjustment Note", "Reason for adjustment (required):")
        if not ok or not note:
            QMessageBox.warning(self, "Required", "A reason is required for adjustments.")
            return

        current_user = AuthService.get_current_user()
        if not current_user:
            QMessageBox.warning(self, "Error", "No user logged in.")
            return

        try:
            CustomerCreditService.record_adjustment(
                customer_id=self.selected_customer.id,
                amount=amount,
                note=note,
                user_id=current_user.id,
            )
            QMessageBox.information(self, "Done", "Balance adjusted successfully.")
            # Refresh
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)
            self.reload_ledger()
            self.load_customers()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def edit_customer(self) -> None:
        """Open the customer editor for the selected customer."""
        if not self.selected_customer:
            QMessageBox.warning(self, "No Customer", "Please select a customer first.")
            return

        dialog = CustomerEditor(self.selected_customer, parent=self)
        if dialog.exec():
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)
            self.load_customers()

    def open_add_customer(self) -> None:
        """Open dialog to add a new customer."""
        dialog = CustomerEditor(parent=self)
        if dialog.exec():
            self.load_customers()
