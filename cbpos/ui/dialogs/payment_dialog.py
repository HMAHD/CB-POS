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
    QListWidgetItem,
    QComboBox,
    QCompleter,
    QFrame,
    QSizePolicy,
)

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QDoubleValidator, QKeySequence, QShortcut, QIcon
from cbpos.core.services.payment_service import PaymentService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t


class PaymentDialog(QDialog):
    def __init__(self, total_amount: Decimal, parent=None):
        super().__init__(parent)
        self.total_amount = total_amount
        self.payments = []  # List of {'method': str, 'amount': Decimal}
        self.customer_id = None
        self.payment_methods = []

        self.setWindowTitle(_t("payment.title"))
        self.setFixedSize(920, 700)
        self.setObjectName("PaymentDialog")

        self.load_payment_methods()
        self.init_ui()
        self.setup_shortcuts()

        # Disable parent Enter shortcuts while this dialog is open
        self._disabled_shortcuts: list[QShortcut] = []
        if parent is not None:
            for attr_name in ("shortcut_enter", "shortcut_num_enter"):
                shortcut = getattr(parent, attr_name, None)
                if shortcut and shortcut.isEnabled():
                    shortcut.setEnabled(False)
                    self._disabled_shortcuts.append(shortcut)

    def done(self, result: int) -> None:
        """Re-enable parent shortcuts before closing."""
        for shortcut in self._disabled_shortcuts:
            shortcut.setEnabled(True)
        self._disabled_shortcuts.clear()
        super().done(result)

    def load_payment_methods(self):
        self.payment_methods = PaymentService.get_active_methods()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── Top Banner ───────────────────────────────────────────
        self.lbl_remaining = QLabel("")
        self.lbl_remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_remaining.setObjectName("PaymentRemainingLabel")
        main_layout.addWidget(self.lbl_remaining)

        # ── Content Area (Left: Methods + List | Right: Numpad) ──
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # --- LEFT COLUMN: Method Tiles + Applied Payments ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Section Header: Payment Method
        self.lbl_methods = QLabel("")
        self.lbl_methods.setObjectName("PaymentMethodsHeader")
        left_layout.addWidget(self.lbl_methods)

        # Method Tiles — build rows of 2 with explicit HBox spacing
        self._method_buttons = []
        current_row_layout = None
        for i, method in enumerate(self.payment_methods):
            if i % 2 == 0:
                current_row_layout = QHBoxLayout()
                current_row_layout.setSpacing(12)
                left_layout.addLayout(current_row_layout)

            btn = QPushButton()
            btn.setFixedHeight(56)
            btn.setObjectName("PayMethodBtn")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            if method.is_cash:
                btn.setProperty("methodType", "cash")
            else:
                btn.setProperty("methodType", "other")

            btn_inner = QVBoxLayout(btn)
            btn_inner.setContentsMargins(6, 4, 6, 4)
            btn_inner.setSpacing(0)

            # Shortcut badge in top-right corner
            if method.shortcut:
                lbl_sc = QLabel(method.shortcut)
                lbl_sc.setObjectName("PayMethodShortcut")
                lbl_sc.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
                btn_inner.addWidget(lbl_sc)
            else:
                btn_inner.addStretch()

            lbl_name = QLabel(method.name.upper())
            lbl_name.setObjectName("PayMethodName")
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_inner.addWidget(lbl_name)
            btn_inner.addStretch()

            btn.clicked.connect(lambda checked, m=method, b=btn: self.select_method(m, b))
            current_row_layout.addWidget(btn)
            self._method_buttons.append((btn, method))

        # Pad last row if odd number of methods
        if len(self.payment_methods) % 2 == 1 and current_row_layout:
            current_row_layout.addStretch()

        # Customer Combo (shown only for CREDIT)
        self.lbl_customer = QLabel("")
        self.lbl_customer.setObjectName("PaymentFieldLabel")
        self.cmb_customer = QComboBox()
        self.cmb_customer.setObjectName("PaymentCustomerCombo")
        self.load_customers()
        self.lbl_customer.setVisible(False)
        self.cmb_customer.setVisible(False)
        left_layout.addWidget(self.lbl_customer)
        left_layout.addWidget(self.cmb_customer)

        # Section Header: Applied Payments
        self.lbl_applied = QLabel("")
        self.lbl_applied.setObjectName("PaymentMethodsHeader")
        left_layout.addWidget(self.lbl_applied)

        # Payment List — compact, grows only as needed
        self.list_payments = QListWidget()
        self.list_payments.setObjectName("PaymentList")
        self.list_payments.setMaximumHeight(160)
        self.list_payments.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left_layout.addWidget(self.list_payments)

        left_layout.addStretch()
        content_layout.addWidget(left_widget, stretch=4)

        # --- RIGHT COLUMN: Amount Input + Numpad + Add Button ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Selected method label
        self.lbl_selected_method = QLabel("")
        self.lbl_selected_method.setObjectName("PaymentMethodLabel")
        self.lbl_selected_method.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.lbl_selected_method)

        # Amount Input
        self.txt_amount = QLineEdit()
        self.txt_amount.setObjectName("PaymentAmountInput")
        self.txt_amount.setPlaceholderText("")
        self.txt_amount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_amount.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        self.txt_amount.returnPressed.connect(self.add_payment)
        right_layout.addWidget(self.txt_amount)

        # Numpad Grid — wrapped in container to prevent stretching
        _BTN_SIZE = 72
        _SPACING = 8
        numpad_widget = QWidget()
        numpad_widget.setObjectName("PaymentListItemWidget")
        numpad_w = _BTN_SIZE * 3 + _SPACING * 2  # 3 cols + 2 gaps = 232
        numpad_h = _BTN_SIZE * 4 + _SPACING * 3  # 4 rows + 3 gaps = 312
        numpad_widget.setFixedSize(numpad_w, numpad_h)
        numpad_grid = QGridLayout(numpad_widget)
        numpad_grid.setContentsMargins(0, 0, 0, 0)
        numpad_grid.setHorizontalSpacing(_SPACING)
        numpad_grid.setVerticalSpacing(_SPACING)

        numpad_keys = [
            ("7", 0, 0),
            ("8", 0, 1),
            ("9", 0, 2),
            ("4", 1, 0),
            ("5", 1, 1),
            ("6", 1, 2),
            ("1", 2, 0),
            ("2", 2, 1),
            ("3", 2, 2),
            ("C", 3, 0),
            ("0", 3, 1),
            (".", 3, 2),
        ]

        for key, r, c in numpad_keys:
            btn = QPushButton(key)
            btn.setObjectName("NumpadBtn")
            btn.setFixedSize(_BTN_SIZE, _BTN_SIZE)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            if key == "C":
                btn.setProperty("btnType", "clear")
                btn.clicked.connect(self._on_numpad_clear)
            elif key == ".":
                btn.clicked.connect(self._on_numpad_dot)
            else:
                btn.clicked.connect(lambda checked, d=key: self._on_numpad_digit(d))

            numpad_grid.addWidget(btn, r, c)

        # Center the numpad
        numpad_wrapper = QHBoxLayout()
        numpad_wrapper.addStretch()
        numpad_wrapper.addWidget(numpad_widget)
        numpad_wrapper.addStretch()
        right_layout.addLayout(numpad_wrapper)

        # Add Payment Button
        self.btn_add = QPushButton("")
        self.btn_add.setObjectName("BtnAddPayment")
        self.btn_add.setFixedHeight(48)
        self.btn_add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_add.clicked.connect(self.add_payment)
        right_layout.addWidget(self.btn_add)

        right_layout.addStretch()
        content_layout.addWidget(right_widget, stretch=5)

        main_layout.addLayout(content_layout, stretch=1)

        # ── Bottom Action Bar ────────────────────────────────────
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("PaymentSeparator")
        main_layout.addWidget(separator)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        self.btn_cancel = QPushButton("")
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setFixedHeight(48)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_finish = QPushButton("")
        self.btn_finish.setObjectName("BtnFinishSale")
        self.btn_finish.setFixedHeight(48)
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self._finish_sale)

        action_layout.addWidget(self.btn_cancel, stretch=1)
        action_layout.addWidget(self.btn_finish, stretch=2)
        main_layout.addLayout(action_layout)

        # Auto-select first method
        self.current_method = None
        self._active_btn = None
        if self.payment_methods:
            first_btn = self._method_buttons[0][0]
            self.select_method(self.payment_methods[0], first_btn)

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("payment.title"))
        self.lbl_remaining.setText(f"{_t('payment.remaining')} {format_currency(self.total_amount)}")
        self.lbl_methods.setText(_t("payment.method_label"))
        self.lbl_customer.setText(_t("payment.customer_label"))
        self.lbl_applied.setText(_t("payment.applied_label"))
        self.txt_amount.setPlaceholderText(_t("payment.enter_amount_placeholder"))
        self.btn_add.setText(_t("payment.add_payment"))
        self.btn_cancel.setText(_t("payment.cancel"))
        self.btn_finish.setText(_t("payment.finish_sale"))

    def setup_shortcuts(self):
        # Dialog-scoped Enter shortcut to add payment
        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(self.add_payment)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self).activated.connect(self.add_payment)

        # F12 Quick Pay (Cash)
        self.shortcut_f12 = QShortcut(QKeySequence("F12"), self)
        self.shortcut_f12.activated.connect(self.quick_pay_cash)

        # Dynamic shortcuts from DB
        for btn, method in self._method_buttons:
            if method.shortcut:
                try:
                    sc = QShortcut(QKeySequence(method.shortcut), self)
                    sc.activated.connect(lambda m=method, b=btn: self.select_method(m, b))
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).warning("Invalid shortcut '%s': %s", method.shortcut, e)

    def load_customers(self):
        customers = CustomerService().get_all_customers()
        self.customers_map = {c.name: c.id for c in customers}
        names = list(self.customers_map.keys())
        self.cmb_customer.addItems(names)
        # Make searchable — type to filter
        self.cmb_customer.setEditable(True)
        self.cmb_customer.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.cmb_customer.lineEdit().setPlaceholderText(_t("payment.search_customer_placeholder"))
        completer = QCompleter(names, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.cmb_customer.setCompleter(completer)

    def select_method(self, method, btn: QPushButton = None):
        self.current_method = method
        self.lbl_selected_method.setText(method.name)

        # Update active tile styling via properties (no inline stylesheets)
        if self._active_btn:
            self._active_btn.setProperty("selected", False)
            self._active_btn.style().unpolish(self._active_btn)
            self._active_btn.style().polish(self._active_btn)

        if btn:
            btn.setProperty("selected", True)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            self._active_btn = btn

        # Show customer combo for CREDIT only
        from cbpos.core.constants.status import PaymentMethodType

        is_credit = method.name.upper() == PaymentMethodType.CREDIT.upper()
        self.lbl_customer.setVisible(is_credit)
        self.cmb_customer.setVisible(is_credit)

        # Auto-fill remaining amount for all methods
        remaining = self.get_remaining_amount()
        if remaining > 0:
            self.txt_amount.setText(f"{remaining:.2f}")  # noqa: E231
        else:
            self.txt_amount.clear()

        self.txt_amount.setFocus()
        self.txt_amount.selectAll()

    def quick_pay_cash(self):
        """Find Cash method, auto-fill exact amount, and submit."""
        cash_method = None
        cash_btn = None
        for btn, method in self._method_buttons:
            if method.is_cash:
                cash_method = method
                cash_btn = btn
                break

        if cash_method:
            self.select_method(cash_method, cash_btn)
            remaining = self.get_remaining_amount()
            if remaining > 0:
                self.txt_amount.setText(f"{remaining:.2f}")  # noqa: E231
                self.add_payment()
                if self.get_remaining_amount() <= 0:
                    self.accept()

    def get_remaining_amount(self) -> Decimal:
        paid = sum(p["amount"] for p in self.payments)
        return self.total_amount - paid

    def add_payment(self):
        from cbpos.core.constants.status import PaymentMethodType

        if not self.current_method:
            return

        text = self.txt_amount.text().strip()
        if not text:
            return

        try:
            amount = Decimal(text)
        except (ValueError, ArithmeticError):
            QMessageBox.warning(self, _t("payment.invalid_amount_title"), _t("payment.invalid_amount_message"))
            return

        if amount <= 0:
            return

        if self.current_method.name.upper() == PaymentMethodType.CREDIT.upper():
            cust_name = self.cmb_customer.currentText().strip()
            if not cust_name:
                QMessageBox.warning(self, _t("common.error"), _t("payment.credit_no_customer"))
                return
            cust_id = self.customers_map.get(cust_name)
            if cust_id is None:
                QMessageBox.warning(
                    self,
                    _t("common.error"),
                    _t("payment.credit_customer_not_found", name=cust_name),
                )
                return
            self.customer_id = cust_id

        self.payments.append({"method": self.current_method.name, "amount": amount})
        self._add_payment_list_item(
            len(self.payments) - 1,
            self.current_method.name,
            amount,
        )

        self.update_balance()
        self.txt_amount.clear()
        self.txt_amount.setFocus()

    def _add_payment_list_item(self, index: int, method_name: str, amount: Decimal):
        """Add a payment entry to the list with a remove button."""
        from pathlib import Path

        item_widget = QWidget()
        item_widget.setObjectName("PaymentListItemWidget")
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(8, 8, 14, 8)
        item_layout.setSpacing(8)

        lbl = QLabel(f"{method_name}: {format_currency(amount)}")
        lbl.setObjectName("PaymentListItemLabel")
        item_layout.addWidget(lbl, stretch=1)

        icon_path = Path(__file__).resolve().parents[2] / "assets" / "icons" / "x-red.svg"
        btn_remove = QPushButton()
        btn_remove.setObjectName("BtnRemovePayment")
        btn_remove.setIcon(QIcon(str(icon_path)))
        btn_remove.setIconSize(QSize(18, 18))
        btn_remove.setFixedSize(44, 44)
        btn_remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_remove.setToolTip(_t("payment.remove_tooltip"))
        btn_remove.clicked.connect(lambda: self._remove_payment(item))
        item_layout.addWidget(btn_remove)

        item = QListWidgetItem()
        hint = item_widget.sizeHint()
        hint.setHeight(max(hint.height(), 48))
        item.setSizeHint(hint)
        self.list_payments.addItem(item)
        self.list_payments.setItemWidget(item, item_widget)

    def _remove_payment(self, item: QListWidgetItem):
        """Remove a payment entry and recalculate balance."""
        row = self.list_payments.row(item)
        if row < 0 or row >= len(self.payments):
            return

        self.payments.pop(row)
        self.list_payments.takeItem(row)
        self.update_balance()

        # Reset to initial state if no payments left
        if not self.payments:
            self.lbl_remaining.setText(f"{_t('payment.remaining')} {format_currency(self.total_amount)}")
            self.lbl_remaining.setProperty("state", "remaining")
            self.lbl_remaining.setStyleSheet("")  # Reset to CSS default
            self.lbl_remaining.style().unpolish(self.lbl_remaining)
            self.lbl_remaining.style().polish(self.lbl_remaining)
            self.btn_finish.setEnabled(False)

    def update_balance(self):
        remaining = self.get_remaining_amount()

        if remaining > 0:
            self.lbl_remaining.setText(f"{_t('payment.remaining')} {format_currency(remaining)}")
            self.lbl_remaining.setProperty("state", "remaining")
            self.lbl_remaining.setStyleSheet("")  # Reset to CSS default
            self.lbl_remaining.style().unpolish(self.lbl_remaining)
            self.lbl_remaining.style().polish(self.lbl_remaining)
            self.btn_finish.setEnabled(False)
            self.txt_amount.setText(str(remaining))
        else:
            change = abs(remaining)
            self.lbl_remaining.setText(f"{_t('payment.change')} {format_currency(change)}")
            self.lbl_remaining.setProperty("state", "change")
            self.lbl_remaining.setStyleSheet("color: #39FF14;")  # Green for change
            self.lbl_remaining.style().unpolish(self.lbl_remaining)
            self.lbl_remaining.style().polish(self.lbl_remaining)
            self.btn_finish.setEnabled(True)
            self.btn_finish.setFocus()

    # ── Numpad Helpers ─────────────────────────────────────────

    def _on_numpad_digit(self, digit: str):
        self.txt_amount.setFocus()
        current = self.txt_amount.text()
        # If text is selected (auto-filled), replace it
        if self.txt_amount.hasSelectedText():
            self.txt_amount.clear()
            current = ""
        self.txt_amount.setText(current + digit)

    def _on_numpad_clear(self):
        self.txt_amount.clear()
        self.txt_amount.setFocus()

    def _on_numpad_dot(self):
        self.txt_amount.setFocus()
        current = self.txt_amount.text()
        if self.txt_amount.hasSelectedText():
            self.txt_amount.clear()
            current = ""
        if "." not in current:
            self.txt_amount.setText(current + ".")

    def _finish_sale(self) -> None:
        """Disable finish button to prevent double-click, then accept."""
        self.btn_finish.setEnabled(False)
        self.accept()

    @property
    def payment_data(self):
        return self.payments, self.customer_id
