import logging
from decimal import Decimal
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
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
from PyQt6.QtGui import QColor, QShortcut, QKeySequence
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.utils.formatters import format_currency
from cbpos.ui.dialogs.customer_editor import CustomerEditor
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.widgets.table_helpers import configure_table_columns

logger = logging.getLogger(__name__)


class CreditBookView(QWidget):
    """
    Drill-down Credit Book view.
    Page 0: Full-width customer list with search and debt indicators.
    Page 1: Selected customer's header, actions, ledger, and summary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("CreditBookView")
        self.customer_service = CustomerService()
        self.selected_customer = None
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))
        self.load_customers()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("CreditBookStack")
        layout.addWidget(self.stack)

        # ===== PAGE 0: Customer List =====
        self._build_customer_list_page()

        # ===== PAGE 1: Customer Detail / Ledger =====
        self._build_customer_detail_page()

    # ------------------------------------------------------------------
    # Page 0: Customer List
    # ------------------------------------------------------------------

    def _build_customer_list_page(self) -> None:
        page = QWidget()
        page.setObjectName("CreditListPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 16, 16, 16)
        page_layout.setSpacing(12)

        # Header row
        header_row = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("CreditPageTitle")
        header_row.addWidget(self.title_label)
        header_row.addStretch()

        self.btn_add_customer = QPushButton()
        self.btn_add_customer.setObjectName("CreditAddBtn")
        self.btn_add_customer.clicked.connect(self.open_add_customer)
        header_row.addWidget(self.btn_add_customer)
        page_layout.addLayout(header_row)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setObjectName("CreditSearchInput")
        self.search_input.textChanged.connect(self.filter_customers)
        page_layout.addWidget(self.search_input)

        # Customer table (full width)
        self.customer_table = QTableWidget()
        self.customer_table.setObjectName("CreditCustomerTable")
        self.customer_table.setColumnCount(5)
        configure_table_columns(
            self.customer_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # ID (hidden)
                1: QHeaderView.ResizeMode.Stretch,  # Name - needs the room
                2: QHeaderView.ResizeMode.ResizeToContents,  # Phone
                3: QHeaderView.ResizeMode.ResizeToContents,  # Outstanding Debt
                4: QHeaderView.ResizeMode.ResizeToContents,  # Credit Limit
            },
        )
        self.customer_table.setColumnHidden(0, True)
        self.customer_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.customer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.customer_table.setAlternatingRowColors(True)
        self.customer_table.verticalHeader().setVisible(False)
        self.customer_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.customer_table.doubleClicked.connect(self._on_customer_double_click)
        page_layout.addWidget(self.customer_table, 1)

        open_row = QHBoxLayout()
        open_row.addStretch()
        self.btn_open_customer_ledger = QPushButton()
        self.btn_open_customer_ledger.setObjectName("BtnOpenCustomerLedger")
        self.btn_open_customer_ledger.clicked.connect(self._open_selected_customer)
        open_row.addWidget(self.btn_open_customer_ledger)
        page_layout.addLayout(open_row)

        QShortcut(QKeySequence(Qt.Key.Key_Return), self.customer_table).activated.connect(self._open_selected_customer)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self.customer_table).activated.connect(self._open_selected_customer)

        # Summary footer
        footer = QFrame()
        footer.setObjectName("CreditListFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        self.lbl_total_customers = QLabel()
        self.lbl_total_customers.setObjectName("CreditFooterLabel")
        self.lbl_total_outstanding = QLabel()
        self.lbl_total_outstanding.setObjectName("CreditFooterDebt")
        footer_layout.addWidget(self.lbl_total_customers)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_total_outstanding)
        page_layout.addWidget(footer)

        self.stack.addWidget(page)

    # ------------------------------------------------------------------
    # Page 1: Customer Detail / Ledger
    # ------------------------------------------------------------------

    def _build_customer_detail_page(self) -> None:
        page = QWidget()
        page.setObjectName("CreditDetailPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 16, 16, 16)
        page_layout.setSpacing(12)

        # Back button + title row
        nav_row = QHBoxLayout()
        self.btn_back = QPushButton()
        self.btn_back.setObjectName("CreditBackBtn")
        self.btn_back.clicked.connect(self._go_back)
        nav_row.addWidget(self.btn_back)
        nav_row.addStretch()
        page_layout.addLayout(nav_row)

        # Customer Header Card
        self.header_card = QFrame()
        self.header_card.setObjectName("CreditHeaderCard")
        header_layout = QVBoxLayout(self.header_card)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(8)

        # Row 1: Name + Phone
        row1 = QHBoxLayout()
        self.lbl_cust_name = QLabel()
        self.lbl_cust_name.setObjectName("CreditCustName")
        self.lbl_cust_phone = QLabel("")
        self.lbl_cust_phone.setObjectName("CreditCustPhone")
        row1.addWidget(self.lbl_cust_name)
        row1.addStretch()
        row1.addWidget(self.lbl_cust_phone)
        header_layout.addLayout(row1)

        # Row 2: Metric cards
        row2 = QHBoxLayout()
        row2.setSpacing(16)
        self.lbl_debt = QLabel()
        self.lbl_debt.setObjectName("CreditMetricDebt")
        self.lbl_available = QLabel()
        self.lbl_available.setObjectName("CreditMetricAvail")
        self.lbl_last_payment = QLabel()
        self.lbl_last_payment.setObjectName("CreditMetricLast")
        row2.addWidget(self.lbl_debt)
        row2.addWidget(self.lbl_available)
        row2.addStretch()
        row2.addWidget(self.lbl_last_payment)
        header_layout.addLayout(row2)

        page_layout.addWidget(self.header_card)

        # Action Buttons
        action_bar = QFrame()
        action_bar.setObjectName("CreditActionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)

        self.btn_receive_payment = QPushButton()
        self.btn_receive_payment.setObjectName("CreditPayBtn")
        self.btn_receive_payment.clicked.connect(self.receive_payment)
        action_layout.addWidget(self.btn_receive_payment)

        self.btn_print_statement = QPushButton()
        self.btn_print_statement.setObjectName("CreditPrintBtn")
        self.btn_print_statement.clicked.connect(self.print_statement)
        action_layout.addWidget(self.btn_print_statement)

        self.btn_adjust = QPushButton()
        self.btn_adjust.setObjectName("CreditAdjustBtn")
        self.btn_adjust.clicked.connect(self.adjust_balance)
        action_layout.addWidget(self.btn_adjust)

        self.btn_edit_customer = QPushButton()
        self.btn_edit_customer.setObjectName("CreditEditBtn")
        self.btn_edit_customer.clicked.connect(self.edit_customer)
        action_layout.addWidget(self.btn_edit_customer)

        action_layout.addStretch()
        page_layout.addWidget(action_bar)

        # Date Filters
        filter_bar = QFrame()
        filter_bar.setObjectName("CreditFilterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)

        self.lbl_from = QLabel()
        self.lbl_from.setObjectName("CreditFilterLabel")
        filter_layout.addWidget(self.lbl_from)
        self.date_from = QDateEdit()
        self.date_from.setObjectName("CreditDateEdit")
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_from.dateChanged.connect(self.reload_ledger)
        filter_layout.addWidget(self.date_from)

        self.lbl_to = QLabel()
        self.lbl_to.setObjectName("CreditFilterLabel")
        filter_layout.addWidget(self.lbl_to)
        self.date_to = QDateEdit()
        self.date_to.setObjectName("CreditDateEdit")
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self.reload_ledger)
        filter_layout.addWidget(self.date_to)

        self.btn_all_dates = QPushButton()
        self.btn_all_dates.setObjectName("CreditAllDatesBtn")
        self.btn_all_dates.clicked.connect(self.show_all_dates)
        filter_layout.addWidget(self.btn_all_dates)

        filter_layout.addStretch()
        page_layout.addWidget(filter_bar)

        # Ledger Table (full width)
        self.ledger_table = QTableWidget()
        self.ledger_table.setObjectName("CreditLedgerTable")
        self.ledger_table.setColumnCount(6)
        self.ledger_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.ledger_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ledger_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ledger_table.setAlternatingRowColors(True)
        self.ledger_table.verticalHeader().setVisible(False)
        self.ledger_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page_layout.addWidget(self.ledger_table, 1)

        # Footer Summary
        footer = QFrame()
        footer.setObjectName("CreditLedgerFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        self.lbl_total_sales = QLabel()
        self.lbl_total_sales.setObjectName("CreditLedgerDebit")
        self.lbl_total_payments = QLabel()
        self.lbl_total_payments.setObjectName("CreditLedgerCredit")
        self.lbl_closing = QLabel()
        self.lbl_closing.setObjectName("CreditLedgerClosing")
        footer_layout.addWidget(self.lbl_total_sales)
        footer_layout.addWidget(self.lbl_total_payments)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_closing)
        page_layout.addWidget(footer)

        self.stack.addWidget(page)

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.title_label.setText(_t("credit_book.title"))
        self.btn_add_customer.setText(_t("credit_book.btn_add_customer"))
        self.btn_open_customer_ledger.setText(_t("credit_book.btn_open_customer_ledger"))
        self.search_input.setPlaceholderText(_t("credit_book.search_placeholder"))
        self.customer_table.setHorizontalHeaderLabels(
            [
                _t("credit_book.customer_header_id"),
                _t("credit_book.customer_header_name"),
                _t("credit_book.customer_header_phone"),
                _t("credit_book.customer_header_debt"),
                _t("credit_book.customer_header_limit"),
            ]
        )
        self.btn_back.setText(_t("credit_book.btn_back"))
        self.btn_receive_payment.setText(_t("credit_book.btn_receive_payment"))
        self.btn_print_statement.setText(_t("credit_book.btn_print_statement"))
        self.btn_adjust.setText(_t("credit_book.btn_adjust_balance"))
        self.btn_edit_customer.setText(_t("credit_book.btn_edit_customer"))
        self.lbl_from.setText(_t("credit_book.from"))
        self.lbl_to.setText(_t("credit_book.to"))
        self.btn_all_dates.setText(_t("credit_book.all"))
        self.ledger_table.setHorizontalHeaderLabels(
            [
                _t("credit_book.ledger_header_date"),
                _t("credit_book.ledger_header_type"),
                _t("credit_book.ledger_header_doc"),
                _t("credit_book.ledger_header_debit"),
                _t("credit_book.ledger_header_credit"),
                _t("credit_book.ledger_header_balance"),
            ]
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_customer_double_click(self, index) -> None:
        """Drill into the selected customer's ledger."""
        self._open_customer_row(index.row())

    def _open_selected_customer(self) -> None:
        """Drill into the currently selected customer's ledger (button/Enter key)."""
        self._open_customer_row(self.customer_table.currentRow())

    def _open_customer_row(self, row: int) -> None:
        """Drill into the ledger for the given table row."""
        if row < 0:
            return
        customer_id_item = self.customer_table.item(row, 0)
        if not customer_id_item:
            return

        customer_id = int(customer_id_item.text())
        customer = self.customer_service.get_customer(customer_id)
        if customer:
            self.selected_customer = customer
            self.update_header(customer)
            self.reload_ledger()
            self.stack.setCurrentIndex(1)

    def _go_back(self) -> None:
        """Return to the customer list."""
        self.stack.setCurrentIndex(0)
        self.load_customers()

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

        if not customers:
            self.customer_table.insertRow(0)
            empty_item = QTableWidgetItem(_t("credit_book.no_customers_found"))
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(QColor("gray"))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.customer_table.setItem(0, 0, empty_item)
            self.customer_table.setSpan(0, 0, 1, self.customer_table.columnCount())
            self.lbl_total_customers.setText(_t("credit_book.customer_count", count=0))
            self.lbl_total_outstanding.setText(
                _t("credit_book.total_outstanding", amount=format_currency(Decimal("0.00")))
            )
            return

        total_outstanding = Decimal("0.00")

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
                    debt_item.setForeground(QColor("#FF4136"))
                elif ratio >= Decimal("0.5"):
                    debt_item.setForeground(QColor("#FF851B"))
                elif customer.current_debt == 0:
                    debt_item.setForeground(QColor("#39FF14"))
            elif customer.current_debt > 0:
                debt_item.setForeground(QColor("#FF4136"))

            self.customer_table.setItem(row, 3, debt_item)
            self.customer_table.setItem(row, 4, limit_item)

            total_outstanding += customer.current_debt

        # Update footer
        count = len(customers)
        self.lbl_total_customers.setText(_t("credit_book.customer_count", count=count))
        self.lbl_total_outstanding.setText(
            _t("credit_book.total_outstanding", amount=format_currency(total_outstanding))
        )

    def update_header(self, customer) -> None:
        """Update the header card with customer details."""
        self.lbl_cust_name.setText(customer.name)
        self.lbl_cust_phone.setText(customer.phone or _t("credit_book.no_phone"))

        summary = CustomerCreditService.get_customer_summary(customer.id)
        if summary:
            self.lbl_debt.setText(_t("credit_book.debt_label") + " " + format_currency(summary["current_debt"]))
            self.lbl_available.setText(_t("credit_book.available_label") + " " + format_currency(summary["available"]))
            if summary["last_payment_date"]:
                self.lbl_last_payment.setText(
                    _t("credit_book.last_payment_label") + " " + summary["last_payment_date"].strftime("%Y-%m-%d")
                )
            else:
                self.lbl_last_payment.setText(_t("credit_book.last_payment_label") + " " + _t("credit_book.none"))
        else:
            self.lbl_debt.setText(_t("credit_book.debt_label") + " ---")
            self.lbl_available.setText(_t("credit_book.available_label") + " ---")
            self.lbl_last_payment.setText(_t("credit_book.last_payment_label") + " ---")

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
                debit_item = QTableWidgetItem(f"{entry.amount:.2f}")  # noqa: E231
                debit_item.setForeground(QColor("#FF4136"))
                debit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.ledger_table.setItem(row, 3, debit_item)
                self.ledger_table.setItem(row, 4, QTableWidgetItem(""))
                total_debit += entry.amount
            else:
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
        self.lbl_total_sales.setText(_t("credit_book.sales_label") + " " + format_currency(total_debit))
        self.lbl_total_payments.setText(_t("credit_book.payments_label") + " " + format_currency(total_credit))
        self.lbl_closing.setText(_t("credit_book.closing_label") + " " + format_currency(closing_balance))

    # ========== Action Methods ==========

    def receive_payment(self) -> None:
        """Open the Receive Payment dialog for the selected customer."""
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.CREDIT_RECEIVE_PAYMENT, self):
            return

        if not self.selected_customer:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        if self.selected_customer.current_debt <= 0:
            QMessageBox.information(
                self,
                _t("credit_book.no_debt_title"),
                _t("credit_book.no_debt_msg"),
            )
            return

        from cbpos.ui.dialogs.receive_payment_dialog import ReceivePaymentDialog

        dialog = ReceivePaymentDialog(self.selected_customer.id, self)
        if dialog.exec():
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)
            self.reload_ledger()

    def print_statement(self) -> None:
        """Open customer statement dialog for viewing and printing."""
        if not self.selected_customer:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        from cbpos.ui.dialogs.customer_statement_dialog import (
            CustomerStatementDialog,
        )

        dialog = CustomerStatementDialog(self.selected_customer, self)
        dialog.exec()

    def adjust_balance(self) -> None:
        """Adjust the customer's balance (correction)."""
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.CREDIT_ADJUST_BALANCE, self):
            return

        if not self.selected_customer:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        amount_str, ok = QInputDialog.getText(
            self,
            _t("credit_book.adjust_title"),
            _t("credit_book.adjust_prompt"),
        )
        if not ok or not amount_str:
            return

        try:
            amount = Decimal(amount_str)
        except Exception:
            QMessageBox.warning(
                self,
                _t("credit_book.invalid_title"),
                _t("credit_book.invalid_amount_msg"),
            )
            return

        note, ok = QInputDialog.getText(
            self,
            _t("credit_book.adjust_note_title"),
            _t("credit_book.adjust_note_prompt"),
        )
        if not ok or not note:
            QMessageBox.warning(
                self,
                _t("credit_book.required_title"),
                _t("credit_book.reason_required_msg"),
            )
            return

        current_user = AuthService.get_current_user()
        if not current_user:
            QMessageBox.warning(self, _t("common.error"), _t("credit_book.no_user_msg"))
            return

        try:
            CustomerCreditService.record_adjustment(
                customer_id=self.selected_customer.id,
                amount=amount,
                note=note,
                user_id=current_user.id,
            )
            QMessageBox.information(
                self,
                _t("credit_book.done_title"),
                _t("credit_book.balance_adjusted_msg"),
            )
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)
            self.reload_ledger()
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))

    def edit_customer(self) -> None:
        """Open the customer editor for the selected customer."""
        if not self.selected_customer:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        dialog = CustomerEditor(self.selected_customer, parent=self)
        if dialog.exec():
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)

    def open_add_customer(self) -> None:
        """Open dialog to add a new customer."""
        dialog = CustomerEditor(parent=self)
        if dialog.exec():
            self.load_customers()
