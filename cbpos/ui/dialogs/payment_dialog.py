import logging
from decimal import Decimal

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QDoubleValidator, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.payment_service import RESERVED_SHORTCUTS, PaymentService, normalize_shortcut
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.style_helpers import refresh_style
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class PaymentDialog(QDialog):
    """Dialog for splitting checkout payment across one or more methods (cash, card, credit, etc.) and confirming
    the sale."""

    def __init__(self, total_amount: Decimal, parent=None, customer=None):
        """Initialize the dialog for the given total, load payment methods, and disable the parent's Enter
        shortcuts while this dialog is open."""
        super().__init__(parent)
        self.total_amount = total_amount
        self.customer = customer
        self.customer_id = customer.id if customer else None
        self._loyalty_points_redeemed = 0
        self._loyalty_discount_value = Decimal("0.00")
        self.payments = []  # List of {'method': str, 'amount': Decimal}
        self.payment_methods = []

        self.setWindowTitle(_t("payment.title"))
        screen = QApplication.primaryScreen().availableGeometry()
        width = min(920, int(screen.width() * 0.90))
        height = min(700, int(screen.height() * 0.90))
        self.resize(width, height)
        self.setMinimumSize(640, 520)
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
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def done(self, result: int) -> None:
        """Re-enable parent shortcuts before closing."""
        for shortcut in self._disabled_shortcuts:
            shortcut.setEnabled(True)
        self._disabled_shortcuts.clear()
        super().done(result)

    def load_payment_methods(self):
        """Load the active payment methods from PaymentService."""
        self.payment_methods = PaymentService.get_active_methods()

    def init_ui(self):
        """Build the method tiles, applied-payments list, numpad, and action buttons."""
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

        # Loyalty Redemption Panel (ADR-0002)

        self.loyalty_frame = QFrame()
        self.loyalty_frame.setObjectName("PaymentLoyaltyFrame")
        loyalty_layout = QVBoxLayout(self.loyalty_frame)
        loyalty_layout.setContentsMargins(10, 8, 10, 8)
        loyalty_layout.setSpacing(6)

        self.lbl_loyalty_header = QLabel(_t("payment.loyalty_section"))
        self.lbl_loyalty_header.setObjectName("PaymentMethodsHeader")
        loyalty_layout.addWidget(self.lbl_loyalty_header)

        loyalty_row = QHBoxLayout()
        loyalty_row.setSpacing(8)

        self.lbl_loyalty_info = QLabel("")
        self.lbl_loyalty_info.setObjectName("PaymentLoyaltyInfo")
        loyalty_row.addWidget(self.lbl_loyalty_info, stretch=1)

        self.lbl_redeemed = QLabel("")
        self.lbl_redeemed.setObjectName("PaymentLoyaltyRedeemed")
        self.lbl_redeemed.setVisible(False)
        loyalty_row.addWidget(self.lbl_redeemed)

        self.btn_redeem = QPushButton(_t("payment.loyalty_redeem_btn"))
        self.btn_redeem.setObjectName("BtnRedeemLoyalty")
        self.btn_redeem.setFixedHeight(34)
        self.btn_redeem.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_redeem.clicked.connect(self._on_redeem_clicked)
        loyalty_row.addWidget(self.btn_redeem)

        self.btn_cancel_redeem = QPushButton(_t("payment.loyalty_cancel_redeem"))
        self.btn_cancel_redeem.setObjectName("BtnCancelLoyalty")
        self.btn_cancel_redeem.setFixedHeight(34)
        self.btn_cancel_redeem.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_cancel_redeem.setVisible(False)
        self.btn_cancel_redeem.clicked.connect(self.cancel_loyalty_redemption)
        loyalty_row.addWidget(self.btn_cancel_redeem)

        loyalty_layout.addLayout(loyalty_row)
        left_layout.addWidget(self.loyalty_frame)
        self._update_loyalty_display()

        # Section Header: Applied Payments
        self.lbl_applied = QLabel("")
        self.lbl_applied.setObjectName("PaymentMethodsHeader")
        left_layout.addWidget(self.lbl_applied)

        # Payment List — compact, grows only as needed. The cap is raised
        # to fit 4-5 typical split payments (#267): 160px only ever fit
        # ~2.5 rows, so a 3rd+ payment scrolled internally and the row
        # sitting right at the 160px cutoff got visually clipped mid-render.
        # The trailing stretch that used to follow this list handed any
        # leftover vertical space to empty space below instead of the list
        # itself -- giving the list its own layout stretch factor instead
        # makes it the thing that grows into freed-up space, up to the cap.
        self.list_payments = QListWidget()
        self.list_payments.setObjectName("PaymentList")
        self.list_payments.setMaximumHeight(280)
        self.list_payments.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.list_payments, 1)
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
        # Sized from the dialog's own height (computed from screen geometry
        # above, before any numpad button exists) rather than a fixed 72px,
        # so it doesn't overflow a small/low-res window (#210). Read at
        # construction time only — not a live resizeEvent — since the
        # buttons are setFixedSize themselves and would create a circular
        # "panel can't shrink below what the buttons already need" loop if
        # this were recomputed off their own container's size later.
        available_h = self.height() - 220
        _BTN_SIZE = max(56, min(72, available_h // 5))
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
        self.btn_finish.setToolTip(_t("payment.finish_tooltip_remaining", amount=format_currency(self.total_amount)))
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
        """Wire the Enter key, F12 quick-cash shortcut, and each payment method's configured shortcut key."""
        # Dialog-scoped Enter shortcut to add payment
        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(self.add_payment)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self).activated.connect(self.add_payment)

        # F12 Quick Pay (Cash)
        self.shortcut_f12 = QShortcut(QKeySequence("F12"), self)
        self.shortcut_f12.activated.connect(self.quick_pay_cash)

        # Dynamic shortcuts from DB. Two QShortcuts on one key are ambiguous
        # and neither fires, so a stored key that collides with ours or an
        # earlier method's (old DBs, e.g. Cash seeded on F12) is skipped
        # rather than breaking F12/Enter (#640).
        used = set(RESERVED_SHORTCUTS)
        for btn, method in self._method_buttons:
            if not method.shortcut:
                continue
            key = normalize_shortcut(method.shortcut)
            if key in used:
                logger.warning(
                    "Skipping shortcut '%s' for payment method '%s': key already in use",
                    method.shortcut,
                    method.name,
                )
                continue
            seq = QKeySequence(method.shortcut)
            if seq.isEmpty():
                logger.warning("Invalid shortcut '%s' for payment method '%s'", method.shortcut, method.name)
                continue
            used.add(key)
            sc = QShortcut(seq, self)
            sc.activated.connect(lambda m=method, b=btn: self.select_method(m, b))

    def load_customers(self):
        """Populate the searchable customer combo used for CREDIT payments."""
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
        """Set the active payment method, update tile styling, and auto-fill the remaining amount."""
        self.current_method = method
        self.lbl_selected_method.setText(method.name)

        # Update active tile styling via properties (no inline stylesheets)
        if self._active_btn:
            self._active_btn.setProperty("selected", False)
            refresh_style(self._active_btn)

        if btn:
            btn.setProperty("selected", True)
            refresh_style(btn)
            self._active_btn = btn

        # Show customer combo for CREDIT only
        from cbpos.core.constants.status import PaymentMethodType

        is_credit = method.name.upper() == PaymentMethodType.CREDIT.upper()
        self.lbl_customer.setVisible(is_credit)
        self.cmb_customer.setVisible(is_credit)

        # Auto-fill remaining amount for all methods
        remaining = self.get_remaining_amount()
        if remaining > 0:
            self.txt_amount.setText(f"{remaining:.2f}")
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
                self.txt_amount.setText(f"{remaining:.2f}")
                self.add_payment()
                if self.get_remaining_amount() <= 0:
                    self.accept()

    def _update_loyalty_display(self):
        """Update loyalty card display based on attached customer and points."""
        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.services.loyalty_service import LoyaltyService

        if not ConfigService.get("enable_loyalty"):
            self.loyalty_frame.setVisible(False)
            return

        self.loyalty_frame.setVisible(True)
        if self.customer:
            pts = self.customer.loyalty_points or 0
            val = LoyaltyService.calculate_redeem_value(pts)
            self.lbl_loyalty_info.setText(
                f"{self.customer.name} • {_t('payment.loyalty_points_available', points=pts, value=format_currency(val))}"
            )
            self.btn_redeem.setEnabled(pts > 0)
        else:
            self.lbl_loyalty_info.setText(_t("payment.loyalty_no_customer"))
            self.btn_redeem.setEnabled(False)

    def apply_loyalty_redemption(self, points: int) -> bool:
        """Apply points redemption as a rupee discount."""
        from cbpos.core.services.loyalty_service import LoyaltyService

        can_redeem, reason = LoyaltyService.can_redeem_points(self.customer, points, self.total_amount)
        if not can_redeem:
            self._show_loyalty_error(reason, points)
            return False

        self._loyalty_points_redeemed = points
        self._loyalty_discount_value = LoyaltyService.calculate_redeem_value(points)

        self.lbl_redeemed.setText(
            _t("payment.loyalty_redeemed_label", points=points, value=format_currency(self._loyalty_discount_value))
        )
        self.lbl_redeemed.setVisible(True)
        self.btn_cancel_redeem.setVisible(True)
        self.btn_redeem.setVisible(False)

        self.update_balance()
        return True

    def cancel_loyalty_redemption(self):
        """Cancel previously applied loyalty points redemption."""
        self._loyalty_points_redeemed = 0
        self._loyalty_discount_value = Decimal("0.00")
        self.lbl_redeemed.setVisible(False)
        self.btn_cancel_redeem.setVisible(False)
        self.btn_redeem.setVisible(True)
        self.update_balance()

    def _on_redeem_clicked(self):
        """Prompt cashier for loyalty points to redeem."""
        from PyQt6.QtWidgets import QInputDialog

        from cbpos.core.services.config_service import ConfigService

        if not self.customer:
            QMessageBox.warning(self, _t("common.error"), _t("payment.loyalty_err_no_customer"))
            return

        pts = self.customer.loyalty_points or 0
        if pts <= 0:
            QMessageBox.warning(self, _t("common.error"), _t("payment.loyalty_err_insufficient", available=0))
            return

        val_cfg = ConfigService.get("loyalty_point_value")
        point_val = Decimal(str(val_cfg or "1.00"))
        max_from_bill = int(self.total_amount // point_val)
        max_points = min(pts, max_from_bill)
        if max_points <= 0:
            QMessageBox.warning(
                self,
                _t("common.error"),
                _t(
                    "payment.loyalty_err_exceeds_bill",
                    value=format_currency(point_val),
                    total=format_currency(self.total_amount),
                ),
            )
            return

        min_redeem = int(ConfigService.get("loyalty_minimum_redeem") or 0)
        max_val_str = format_currency(Decimal(max_points) * point_val)
        points, ok = QInputDialog.getInt(
            self,
            _t("payment.loyalty_dialog_title"),
            _t("payment.loyalty_dialog_prompt", max=max_points, max_val=max_val_str),
            max_points,
            max(1, min_redeem),
            pts,
            1,
        )
        if ok:
            self.apply_loyalty_redemption(points)

    def _show_loyalty_error(self, reason: str, points: int):
        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.services.loyalty_service import LoyaltyService

        min_redeem = int(ConfigService.get("loyalty_minimum_redeem") or 0)
        available = (self.customer.loyalty_points or 0) if self.customer else 0
        val_str = format_currency(LoyaltyService.calculate_redeem_value(points))
        tot_str = format_currency(self.total_amount)

        msgs = {
            "loyalty_disabled": _t("payment.loyalty_err_disabled"),
            "no_customer": _t("payment.loyalty_err_no_customer"),
            "customer_not_found": _t("payment.loyalty_err_no_customer"),
            "invalid_points": _t("payment.loyalty_err_invalid"),
            "insufficient_points": _t("payment.loyalty_err_insufficient", available=available),
            "below_minimum": _t("payment.loyalty_err_min_redeem", min=min_redeem),
            "exceeds_bill": _t("payment.loyalty_err_exceeds_bill", value=val_str, total=tot_str),
        }
        msg = msgs.get(reason, str(reason))
        QMessageBox.warning(self, _t("common.error"), msg)

    def get_remaining_amount(self) -> Decimal:
        """Return the amount still owed after payments already applied and loyalty discount."""
        paid = sum(p["amount"] for p in self.payments)
        effective_total = self.total_amount - self._loyalty_discount_value
        return effective_total - paid

    def add_payment(self):
        """Validate the entered amount and append it as a payment for the current method, requiring a
        customer for CREDIT."""
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
        """Add a payment entry to the list with a remove button.

        The row separator used to be QListWidget::item's own QSS
        border-bottom (plus padding). That box model is invisible to
        Qt's layout code -- it's applied by the view AFTER
        setSizeHint() reserves a rect, not accounted for inside it -- so
        no fixed pixel buffer added to the sizeHint here could reliably
        match it across different fonts/platforms/DPI (confirmed: it
        clipped the fixed 44px remove button's bottom border in
        production despite a manually tuned buffer that looked correct
        in local testing). Drawing the separator as a real child widget
        inside item_widget instead means item_widget.sizeHint() is the
        complete, exact truth -- nothing external can silently eat into
        the space Qt reserves for it.
        """
        item_widget = QWidget()
        item_widget.setObjectName("PaymentListItemWidget")
        outer_layout = QVBoxLayout(item_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        row_widget = QWidget()
        row_widget.setObjectName("PaymentListItemRow")
        item_layout = QHBoxLayout(row_widget)
        item_layout.setContentsMargins(8, 8, 14, 8)
        item_layout.setSpacing(8)

        lbl = QLabel(f"{method_name}: {format_currency(amount)}")
        lbl.setObjectName("PaymentListItemLabel")
        item_layout.addWidget(lbl, stretch=1)

        # Uses the app's centralized qtawesome icon system (cbpos/ui/resources/icons.py)
        # rather than loading a raw SVG file directly -- a raw QIcon(path) depends on
        # Qt's SVG icon engine plugin being present, which isn't guaranteed on every
        # install; qtawesome renders from a bundled font instead, matching every other
        # icon in the app and avoiding that dependency.
        btn_remove = QPushButton()
        btn_remove.setObjectName("BtnRemovePayment")
        btn_remove.setIcon(Icons.get(Icons.CANCEL, color="#FF4136"))
        btn_remove.setIconSize(QSize(18, 18))
        btn_remove.setFixedSize(44, 44)
        btn_remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_remove.setToolTip(_t("payment.remove_tooltip"))
        btn_remove.clicked.connect(lambda: self._remove_payment(item))
        item_layout.addWidget(btn_remove)

        outer_layout.addWidget(row_widget)

        separator = QFrame()
        separator.setObjectName("PaymentListItemSeparator")
        separator.setFixedHeight(1)
        outer_layout.addWidget(separator)

        item = QListWidgetItem()
        item.setSizeHint(item_widget.sizeHint())
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
            rem = self.get_remaining_amount()
            self.lbl_remaining.setText(f"{_t('payment.remaining')} {format_currency(rem)}")
            self.lbl_remaining.setProperty("state", "remaining")
            refresh_style(self.lbl_remaining)
            self.btn_finish.setEnabled(False)
            self.btn_finish.setToolTip(_t("payment.finish_tooltip_remaining", amount=format_currency(rem)))

    def update_balance(self):
        """Refresh the remaining/change label and enable Finish once the total is fully covered."""
        remaining = self.get_remaining_amount()

        if remaining > 0:
            if self._loyalty_points_redeemed > 0:
                self.lbl_remaining.setText(
                    f"{_t('payment.remaining')} {format_currency(remaining)} "
                    f"(-{format_currency(self._loyalty_discount_value)})"
                )
            else:
                self.lbl_remaining.setText(f"{_t('payment.remaining')} {format_currency(remaining)}")
            self.lbl_remaining.setProperty("state", "remaining")
            refresh_style(self.lbl_remaining)
            self.btn_finish.setEnabled(False)
            self.btn_finish.setToolTip(_t("payment.finish_tooltip_remaining", amount=format_currency(remaining)))
            self.txt_amount.setText(str(remaining))
        else:
            change = abs(remaining)
            self.lbl_remaining.setText(f"{_t('payment.change')} {format_currency(change)}")
            self.lbl_remaining.setProperty("state", "change")
            refresh_style(self.lbl_remaining)
            self.btn_finish.setEnabled(True)
            self.btn_finish.setToolTip("")
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
    def loyalty_points_redeemed(self) -> int:
        """Return whole number of loyalty points redeemed as discount."""
        return self._loyalty_points_redeemed

    @property
    def payment_data(self):
        """Return the list of applied payments and the selected customer id, if any."""
        return self.payments, self.customer_id
