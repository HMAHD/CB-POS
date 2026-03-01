from decimal import Decimal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QGridLayout,
    QMessageBox,
    QWidget,
    QListWidget,
    QComboBox,
    QFrame,
)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator, QKeySequence, QShortcut
from cbpos.core.services.payment_service import PaymentService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.utils.formatters import format_currency


class PaymentDialog(QDialog):
    def __init__(self, total_amount: Decimal, parent=None):
        super().__init__(parent)
        self.total_amount = total_amount
        self.payments = []  # List of {'method': str, 'amount': Decimal}
        self.customer_id = None
        self.payment_methods = []

        self.setWindowTitle("Payment")
        self.setFixedSize(720, 520)
        self.setObjectName("PaymentDialog")

        self.load_payment_methods()
        self.init_ui()
        self.setup_shortcuts()

    def load_payment_methods(self):
        self.payment_methods = PaymentService.get_active_methods()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # ── Total Display Banner ───────────────────────────────────
        self.lbl_remaining = QLabel(f"Total: {format_currency(self.total_amount)}")
        self.lbl_remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_remaining.setObjectName("PaymentRemainingLabel")
        main_layout.addWidget(self.lbl_remaining)

        # ── Content Area (Left: Entry + List | Right: Method Grid) ─
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # --- LEFT: Entry Form + Payment List ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # Entry Group
        entry_group = QFrame()
        entry_group.setObjectName("PaymentEntryGroup")
        entry_layout = QGridLayout(entry_group)
        entry_layout.setContentsMargins(12, 12, 12, 12)
        entry_layout.setHorizontalSpacing(10)
        entry_layout.setVerticalSpacing(8)

        lbl_method = QLabel("Method:")
        lbl_method.setObjectName("PaymentFieldLabel")
        entry_layout.addWidget(lbl_method, 0, 0)

        self.lbl_selected_method = QLabel("Cash")
        self.lbl_selected_method.setObjectName("PaymentMethodLabel")
        entry_layout.addWidget(self.lbl_selected_method, 0, 1)

        lbl_amount = QLabel("Amount:")
        lbl_amount.setObjectName("PaymentFieldLabel")
        entry_layout.addWidget(lbl_amount, 1, 0)

        self.txt_amount = QLineEdit()
        self.txt_amount.setObjectName("PaymentAmountInput")
        self.txt_amount.setPlaceholderText("Enter amount")
        self.txt_amount.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        self.txt_amount.returnPressed.connect(self.add_payment)
        entry_layout.addWidget(self.txt_amount, 1, 1)

        # Customer Selection (Hidden by default)
        self.lbl_customer = QLabel("Customer:")
        self.lbl_customer.setObjectName("PaymentFieldLabel")
        self.cmb_customer = QComboBox()
        self.cmb_customer.setObjectName("PaymentCustomerCombo")
        self.load_customers()
        self.lbl_customer.setVisible(False)
        self.cmb_customer.setVisible(False)
        entry_layout.addWidget(self.lbl_customer, 2, 0)
        entry_layout.addWidget(self.cmb_customer, 2, 1)

        btn_add = QPushButton("ADD PAYMENT")
        btn_add.setObjectName("BtnAddPayment")
        btn_add.clicked.connect(self.add_payment)
        entry_layout.addWidget(btn_add, 3, 0, 1, 2)

        left_layout.addWidget(entry_group)

        # Payment List
        self.list_payments = QListWidget()
        self.list_payments.setObjectName("PaymentList")
        left_layout.addWidget(self.list_payments)

        content_layout.addWidget(left_widget, stretch=3)

        # --- RIGHT: Payment Method Buttons ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        lbl_methods = QLabel("Select Tender:")
        lbl_methods.setObjectName("PaymentMethodsHeader")
        right_layout.addWidget(lbl_methods)

        methods_grid = QGridLayout()
        methods_grid.setSpacing(8)

        row, col = 0, 0
        for method in self.payment_methods:
            btn = QPushButton()
            btn.setFixedSize(110, 70)
            btn.setObjectName("PayMethodBtn")

            if method.is_cash:
                btn.setProperty("methodType", "cash")
            else:
                btn.setProperty("methodType", "other")

            # Two-line label: shortcut + name
            btn_layout = QVBoxLayout(btn)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.setSpacing(2)

            if method.shortcut:
                lbl_sc = QLabel(method.shortcut)
                lbl_sc.setObjectName("PayMethodShortcut")
                lbl_sc.setAlignment(Qt.AlignmentFlag.AlignCenter)
                btn_layout.addWidget(lbl_sc)

            lbl_name = QLabel(method.name.upper())
            lbl_name.setObjectName("PayMethodName")
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_layout.addWidget(lbl_name)

            btn.clicked.connect(lambda checked, m=method: self.select_method(m))
            methods_grid.addWidget(btn, row, col)

            col += 1
            if col > 1:
                col = 0
                row += 1

        right_layout.addLayout(methods_grid)
        right_layout.addStretch()
        content_layout.addWidget(right_widget, stretch=2)

        main_layout.addLayout(content_layout)

        # ── Bottom Action Bar ──────────────────────────────────────
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("PaymentSeparator")
        main_layout.addWidget(separator)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        btn_cancel = QPushButton("CANCEL")
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.setFixedHeight(48)
        btn_cancel.clicked.connect(self.reject)

        self.btn_finish = QPushButton("FINISH SALE")
        self.btn_finish.setObjectName("BtnFinishSale")
        self.btn_finish.setFixedHeight(48)
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self.accept)

        action_layout.addWidget(btn_cancel, stretch=1)
        action_layout.addWidget(self.btn_finish, stretch=2)
        main_layout.addLayout(action_layout)

        # Auto-select first method
        self.current_method = None
        if self.payment_methods:
            self.select_method(self.payment_methods[0])

    def setup_shortcuts(self):
        # F12 Quick Pay (Cash)
        self.shortcut_f12 = QShortcut(QKeySequence("F12"), self)
        self.shortcut_f12.activated.connect(self.quick_pay_cash)

        # Dynamic shortcuts from DB
        for method in self.payment_methods:
            if method.shortcut:
                try:
                    sc = QShortcut(QKeySequence(method.shortcut), self)
                    sc.activated.connect(lambda m=method: self.select_method(m))
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).warning("Invalid shortcut '%s': %s", method.shortcut, e)

    def load_customers(self):
        customers = CustomerService().get_all_customers()
        self.customers_map = {c.name: c.id for c in customers}
        self.cmb_customer.addItems(list(self.customers_map.keys()))

    def select_method(self, method):
        self.current_method = method
        self.lbl_selected_method.setText(method.name)

        if not method.is_cash:
            remaining = self.get_remaining_amount()
            if remaining > 0:
                self.txt_amount.setText(f"{remaining:.2f}")
            self.lbl_customer.setVisible(True)
            self.cmb_customer.setVisible(True)
        else:
            self.txt_amount.clear()
            self.lbl_customer.setVisible(False)
            self.cmb_customer.setVisible(False)

        self.txt_amount.setFocus()
        self.txt_amount.selectAll()

    def quick_pay_cash(self):
        """Find Cash method, auto-fill exact amount, and submit."""
        cash_method = next((m for m in self.payment_methods if m.is_cash), None)
        if cash_method:
            self.select_method(cash_method)
            remaining = self.get_remaining_amount()
            if remaining > 0:
                self.txt_amount.setText(f"{remaining:.2f}")
                self.add_payment()
                if self.get_remaining_amount() <= 0:
                    self.accept()

    def get_remaining_amount(self):
        paid = sum(p["amount"] for p in self.payments)
        return self.total_amount - paid

    def add_payment(self):
        if not self.current_method:
            return

        try:
            amount = Decimal(self.txt_amount.text())
        except (ValueError, ArithmeticError):
            QMessageBox.warning(self, "Invalid Amount", "Please enter a valid amount.")
            return

        if amount <= 0:
            return

        if self.current_method.name.upper() == "CREDIT":
            cust_name = self.cmb_customer.currentText()
            if not cust_name:
                QMessageBox.warning(self, "Error", "Please select a customer for Credit sale.")
                return
            self.customer_id = self.customers_map.get(cust_name)

        self.payments.append({"method": self.current_method.name, "amount": amount})
        self.list_payments.addItem(f"{self.current_method.name}: {format_currency(amount)}")

        self.update_balance()
        self.txt_amount.clear()
        self.txt_amount.setFocus()

    def update_balance(self):
        remaining = self.get_remaining_amount()

        if remaining > 0:
            self.lbl_remaining.setText(f"Remaining: {format_currency(remaining)}")
            self.lbl_remaining.setProperty("state", "remaining")
            self.lbl_remaining.style().unpolish(self.lbl_remaining)
            self.lbl_remaining.style().polish(self.lbl_remaining)
            self.btn_finish.setEnabled(False)
            self.txt_amount.setText(str(remaining))
        else:
            change = abs(remaining)
            self.lbl_remaining.setText(f"Change: {format_currency(change)}")
            self.lbl_remaining.setProperty("state", "change")
            self.lbl_remaining.style().unpolish(self.lbl_remaining)
            self.lbl_remaining.style().polish(self.lbl_remaining)
            self.btn_finish.setEnabled(True)
            self.btn_finish.setFocus()

    @property
    def payment_data(self):
        return self.payments, self.customer_id
