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
    QScrollArea,
)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator, QKeySequence, QShortcut
from cbpos.core.database import Database
from cbpos.core.models import Customer
from cbpos.core.services.payment_service import PaymentService


class PaymentDialog(QDialog):
    def __init__(self, total_amount: Decimal, parent=None):
        print("DEBUG: PaymentDialog.__init__ started")
        super().__init__(parent)
        self.total_amount = total_amount
        self.payments = []  # List of {'method': str, 'amount': Decimal}
        self.customer_id = None
        self.payment_methods = []

        self.setWindowTitle("Payment")
        self.setFixedSize(800, 600)  # Wider for side-by-side layout
        self.setFixedSize(800, 600)  # Wider for side-by-side layout
        self.setObjectName("PaymentDialog")

        print("DEBUG: Loading payment methods...")
        self.load_payment_methods()
        print(f"DEBUG: Loaded {len(self.payment_methods)} payment methods")

        print("DEBUG: Initializing UI...")
        self.init_ui()
        print("DEBUG: Setting up shortcuts...")
        self.setup_shortcuts()
        print("DEBUG: PaymentDialog initialized")

    def load_payment_methods(self):
        self.payment_methods = PaymentService.get_active_methods()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(20)

        # --- LEFT PANEL: Inputs & List ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Total/Remaining Display
        self.lbl_remaining = QLabel(
            f"Total: Rs. {self.total_amount:,.2f}"  # noqa: E231
        )
        self.lbl_remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_remaining.setObjectName("PaymentRemainingLabel")
        left_layout.addWidget(self.lbl_remaining)

        # 2. Payment Entry Form
        entry_group = QWidget()
        entry_group.setObjectName("PaymentEntryGroup")
        entry_layout = QGridLayout(entry_group)

        entry_layout.addWidget(QLabel("Method:"), 0, 0)
        self.lbl_selected_method = QLabel("Select Method ->")
        self.lbl_selected_method.setObjectName("PaymentMethodLabel")
        entry_layout.addWidget(self.lbl_selected_method, 0, 1)

        entry_layout.addWidget(QLabel("Amount:"), 1, 0)
        self.txt_amount = QLineEdit()
        self.txt_amount.setPlaceholderText("Amount")
        self.txt_amount.setPlaceholderText("Amount")
        self.txt_amount.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        self.txt_amount.returnPressed.connect(self.add_payment)
        entry_layout.addWidget(self.txt_amount, 1, 1)

        # Customer Selection (Hidden by default)
        self.lbl_customer = QLabel("Customer:")
        self.cmb_customer = QComboBox()
        self.cmb_customer.setObjectName("PaymentCustomerCombo")
        self.load_customers()

        self.lbl_customer.setVisible(False)
        self.cmb_customer.setVisible(False)

        entry_layout.addWidget(self.lbl_customer, 2, 0)
        entry_layout.addWidget(self.cmb_customer, 2, 1)

        btn_add = QPushButton("Add Payment")
        btn_add.setObjectName("BtnAddPayment")
        btn_add.clicked.connect(self.add_payment)
        entry_layout.addWidget(btn_add, 3, 0, 1, 2)

        left_layout.addWidget(entry_group)

        # 3. Payment List
        self.list_payments = QListWidget()
        self.list_payments.setObjectName("PaymentList")
        left_layout.addWidget(self.list_payments)

        # 4. Bottom Actions
        action_layout = QHBoxLayout()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.clicked.connect(self.reject)

        self.btn_finish = QPushButton("FINISH SALE")
        self.btn_finish.setObjectName("BtnFinishSale")
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self.accept)

        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(self.btn_finish)

        left_layout.addLayout(action_layout)

        main_layout.addWidget(left_panel, 2)  # Stretch factor 2

        # --- RIGHT PANEL: Payment Methods ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        lbl_methods = QLabel("Select Tender:")
        lbl_methods.setObjectName("PaymentMethodsHeader")
        right_layout.addWidget(lbl_methods)

        # Scroll Area for methods if many
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("PaymentMethodsScroll")

        methods_container = QWidget()
        self.methods_grid = QGridLayout(methods_container)
        self.methods_grid.setSpacing(10)

        # Generate Buttons
        row, col = 0, 0
        for method in self.payment_methods:
            btn = QPushButton(method.name)
            btn.setFixedSize(100, 80)
            if method.is_cash:
                btn.setProperty("class", "PaymentMethodBtnCash")
            else:
                btn.setProperty("class", "PaymentMethodBtn")

            # Connect
            # Use closure
            btn.clicked.connect(lambda checked, m=method: self.select_method(m))

            self.methods_grid.addWidget(btn, row, col)

            # Add shortcut label if exists
            if method.shortcut:
                lbl_sc = QLabel(method.shortcut, btn)
                lbl_sc.setObjectName("PaymentShortcutLabel")
                lbl_sc.move(5, 5)

            col += 1
            if col > 1:  # 2 columns
                col = 0
                row += 1

        # Add spacer to push up
        self.methods_grid.setRowStretch(row + 1, 1)

        scroll.setWidget(methods_container)
        right_layout.addWidget(scroll)

        main_layout.addWidget(right_panel, 1)  # Stretch factor 1

        # Set initial state
        self.current_method = None
        # Auto-select first method if available
        if self.payment_methods:
            self.select_method(self.payment_methods[0])

    def setup_shortcuts(self):
        # F12 Quick Pay (Find Cash method)
        self.shortcut_f12 = QShortcut(QKeySequence("F12"), self)
        self.shortcut_f12.activated.connect(self.quick_pay_cash)

        # Dynamic shortcuts from DB
        for method in self.payment_methods:
            if method.shortcut:
                try:
                    sc = QShortcut(QKeySequence(method.shortcut), self)
                    sc.activated.connect(lambda m=method: self.select_method(m))
                except Exception:
                    pass

    def load_customers(self):
        db = Database()
        with db.get_session() as session:
            customers = session.query(Customer).all()
            self.customers_map = {c.name: c.id for c in customers}
            self.cmb_customer.addItems(list(self.customers_map.keys()))

    def select_method(self, method):
        self.current_method = method
        self.lbl_selected_method.setText(method.name)

        # Logic based on type
        if not method.is_cash:
            # Auto-fill remaining amount
            remaining = self.get_remaining_amount()
            if remaining > 0:
                self.txt_amount.setText(f"{remaining:.2f}")  # noqa: E231
            self.lbl_customer.setVisible(True)  # Show customer for non-cash (tracking)
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
                self.txt_amount.setText(f"{remaining:.2f}")  # noqa: E231
                self.add_payment()
                # If fully paid, accept
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
        except Exception:
            return

        if amount <= 0:
            return

        # If Credit/Non-Cash, validate customer if needed?
        # For now, we enforce customer only if explicitly Credit?
        # Let's stick to simple logic: If method name is "Credit", require customer.
        if self.current_method.name.upper() == "CREDIT":
            cust_name = self.cmb_customer.currentText()
            if not cust_name:
                QMessageBox.warning(
                    self, "Error", "Please select a customer for Credit sale."
                )
                return
            self.customer_id = self.customers_map.get(cust_name)

        self.payments.append({"method": self.current_method.name, "amount": amount})
        self.list_payments.addItem(
            f"{self.current_method.name}: Rs. {amount:,.2f}"  # noqa: E231
        )

        self.update_balance()
        self.txt_amount.clear()
        self.txt_amount.setFocus()

    def update_balance(self):
        remaining = self.get_remaining_amount()

        if remaining > 0:
            self.lbl_remaining.setText(f"Remaining: Rs. {remaining:,.2f}")  # noqa: E231
            self.lbl_remaining.setProperty("state", "remaining")
            self.lbl_remaining.style().unpolish(self.lbl_remaining)
            self.lbl_remaining.style().polish(self.lbl_remaining)
            self.btn_finish.setEnabled(False)
            self.btn_finish.setEnabled(False)
            self.txt_amount.setText(str(remaining))
        else:
            change = abs(remaining)
            self.lbl_remaining.setText(f"Change: Rs. {change:,.2f}")  # noqa: E231
            self.lbl_remaining.setProperty("state", "change")
            self.lbl_remaining.style().unpolish(self.lbl_remaining)
            self.lbl_remaining.style().polish(self.lbl_remaining)
            self.btn_finish.setEnabled(True)
            self.btn_finish.setEnabled(True)
            self.btn_finish.setFocus()

    @property
    def payment_data(self):
        return self.payments, self.customer_id
