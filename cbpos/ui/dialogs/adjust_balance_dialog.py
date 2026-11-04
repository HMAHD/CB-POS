"""
Dialog for adjusting customer credit balance with signed-mode safety.
"""

import logging
from decimal import Decimal

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency, get_currency_symbol
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


def _set_button_icon(btn: QPushButton, icon_name: str, color: str, pad_right: int = 8, size: int = 14) -> None:
    """Set button icon with transparent trailing padding to ensure clear spacing before label text."""
    base_pixmap = Icons.get(icon_name, color).pixmap(size, size)
    padded = QPixmap(size + pad_right, size)
    padded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(padded)
    painter.drawPixmap(0, 0, base_pixmap)
    painter.end()
    btn.setIconSize(QSize(size + pad_right, size))
    btn.setIcon(QIcon(padded))


class AdjustBalanceDialog(QDialog):
    """
    Dedicated dialog for adjusting a customer's credit debt.
    Replaces chained QInputDialog prompts with a signed-mode segmented toggle,
    strict positive inputs, live formula preview, and chip presets.
    """

    MODE_ADD = "add"
    MODE_REDUCE = "reduce"
    MODE_SET = "set"

    def __init__(self, customer, parent=None):
        super().__init__(parent)
        self.customer = customer
        self.mode = self.MODE_REDUCE  # Default to reducing debt

        self.setWindowTitle(_t("adjust_balance.title"))
        self.setMinimumWidth(480)
        self.setObjectName("AdjustBalanceDialog")

        self._init_ui()
        install_wheel_guard(self)
        self._recalculate()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Customer Hero Card
        header_card = QFrame()
        header_card.setObjectName("AdjustHeaderCard")
        card_layout = QHBoxLayout(header_card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(12)

        lbl_avatar = QLabel()
        lbl_avatar.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(32, 32))
        card_layout.addWidget(lbl_avatar)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        lbl_name = QLabel(self.customer.name)
        lbl_name.setObjectName("AdjustCustName")
        info_layout.addWidget(lbl_name)

        curr_debt = getattr(self.customer, "current_debt", Decimal("0.00")) or Decimal("0.00")
        if curr_debt < 0:
            debt_text = _t("credit.store_credit", amount=format_currency(abs(curr_debt)))
        else:
            debt_text = f"{_t('adjust_balance.current_debt')} {format_currency(curr_debt)}"
        lbl_debt = QLabel(debt_text)
        lbl_debt.setObjectName("AdjustCustDebt")
        info_layout.addWidget(lbl_debt)

        card_layout.addLayout(info_layout)
        card_layout.addStretch()
        layout.addWidget(header_card)

        # 2. Segmented Mode Selector
        mode_label = QLabel(_t("credit_book.ledger_header_type"))
        mode_label.setProperty("class", "muted")
        layout.addWidget(mode_label)

        mode_box = QHBoxLayout()
        mode_box.setSpacing(8)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        self.btn_mode_reduce = QPushButton(_t("adjust_balance.mode_deduct"))
        self.btn_mode_reduce.setCheckable(True)
        self.btn_mode_reduce.setChecked(True)
        self.btn_mode_reduce.setObjectName("ModeReduceBtn")
        self.btn_mode_reduce.clicked.connect(lambda: self.set_mode(self.MODE_REDUCE))
        self.btn_group.addButton(self.btn_mode_reduce)
        mode_box.addWidget(self.btn_mode_reduce)

        self.btn_mode_add = QPushButton(_t("adjust_balance.mode_add"))
        self.btn_mode_add.setCheckable(True)
        self.btn_mode_add.setObjectName("ModeAddBtn")
        self.btn_mode_add.clicked.connect(lambda: self.set_mode(self.MODE_ADD))
        self.btn_group.addButton(self.btn_mode_add)
        mode_box.addWidget(self.btn_mode_add)

        self.btn_mode_set = QPushButton(_t("adjust_balance.mode_set"))
        self.btn_mode_set.setCheckable(True)
        self.btn_mode_set.setObjectName("ModeSetBtn")
        self.btn_mode_set.clicked.connect(lambda: self.set_mode(self.MODE_SET))
        self.btn_group.addButton(self.btn_mode_set)
        mode_box.addWidget(self.btn_mode_set)

        layout.addLayout(mode_box)

        # 3. Amount Input (Strictly Positive)
        amt_label = QLabel(_t("adjust_balance.amount"))
        amt_label.setProperty("class", "muted")
        layout.addWidget(amt_label)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 9999999.99)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setPrefix(f"{get_currency_symbol()} ")
        self.amount_spin.setValue(0.00)
        self.amount_spin.setObjectName("AdjustAmountSpin")
        self.amount_spin.valueChanged.connect(self._recalculate)
        layout.addWidget(self.amount_spin)

        # 4. Live Calculation & Preview Card
        self.preview_card = QFrame()
        self.preview_card.setObjectName("AdjustPreviewCard")
        prev_layout = QVBoxLayout(self.preview_card)
        prev_layout.setContentsMargins(12, 10, 12, 10)
        prev_layout.setSpacing(4)

        self.lbl_formula = QLabel()
        self.lbl_formula.setObjectName("AdjustFormulaLabel")
        prev_layout.addWidget(self.lbl_formula)

        self.lbl_preview = QLabel()
        self.lbl_preview.setObjectName("AdjustPreviewLabel")
        prev_layout.addWidget(self.lbl_preview)

        layout.addWidget(self.preview_card)

        # 5. Reason Input & Chips
        reason_label = QLabel(_t("adjust_balance.reason"))
        reason_label.setProperty("class", "muted")
        layout.addWidget(reason_label)

        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText(_t("adjust_balance.reason_placeholder"))
        self.reason_edit.setObjectName("AdjustReasonEdit")
        self.reason_edit.textChanged.connect(self._recalculate)
        layout.addWidget(self.reason_edit)

        # Quick chips
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)
        chips = [
            "Opening Balance Correction",
            "Goodwill Concession",
            "Returned Goods",
            "Audit Correction",
        ]
        for chip_text in chips:
            btn_chip = QPushButton(chip_text)
            btn_chip.setProperty("class", "chip")
            btn_chip.clicked.connect(lambda _, t=chip_text: self.reason_edit.setText(t))
            chips_layout.addWidget(btn_chip)
        chips_layout.addStretch()
        layout.addLayout(chips_layout)

        # 6. Action buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        self.btn_save = QPushButton(_t("adjust_balance.confirm"))
        self.btn_save.setProperty("class", "accent")
        _set_button_icon(self.btn_save, "fa5s.check", "#FFFFFF", pad_right=8, size=13)
        self.btn_save.clicked.connect(self.save)
        btn_box.addWidget(self.btn_save)

        btn_cancel = QPushButton(_t("common.cancel"))
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.setProperty("class", "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        layout.addLayout(btn_box)

    def set_mode(self, mode: str) -> None:
        """Switch adjustment mode."""
        self.mode = mode
        if mode == self.MODE_REDUCE:
            self.btn_mode_reduce.setChecked(True)
        elif mode == self.MODE_ADD:
            self.btn_mode_add.setChecked(True)
        elif mode == self.MODE_SET:
            self.btn_mode_set.setChecked(True)
        self._recalculate()

    def calculate_delta(self) -> Decimal:
        """Calculate the delta to apply to the debt balance."""
        amount = Decimal(str(self.amount_spin.value()))
        curr = Decimal(str(getattr(self.customer, "current_debt", Decimal("0.00")) or Decimal("0.00")))
        if self.mode == self.MODE_ADD:
            return amount
        elif self.mode == self.MODE_REDUCE:
            return -amount
        else:  # MODE_SET
            return amount - curr

    def calculate_new_balance(self) -> Decimal:
        """Calculate the resulting balance."""
        curr = Decimal(str(getattr(self.customer, "current_debt", Decimal("0.00")) or Decimal("0.00")))
        return curr + self.calculate_delta()

    def _recalculate(self) -> None:
        """Update formula and preview display."""
        curr = Decimal(str(getattr(self.customer, "current_debt", Decimal("0.00")) or Decimal("0.00")))
        amt = Decimal(str(self.amount_spin.value()))
        new_bal = self.calculate_new_balance()

        if self.mode == self.MODE_ADD:
            formula = f"{format_currency(curr)} + {format_currency(amt)}"
        elif self.mode == self.MODE_REDUCE:
            formula = f"{format_currency(curr)} - {format_currency(amt)}"
        else:
            formula = f"= {format_currency(amt)}"

        self.lbl_formula.setText(f"Calculation: {formula}")
        if new_bal < 0:
            self.lbl_preview.setText(_t("credit.store_credit", amount=format_currency(abs(new_bal))))
        else:
            self.lbl_preview.setText(_t("adjust_balance.preview", value=format_currency(new_bal)))

    def validate(self) -> bool:
        """Validate input values."""
        if self.amount_spin.value() <= 0:
            return False
        return bool(self.reason_edit.text().strip())

    def save(self) -> None:
        """Record the balance adjustment."""
        if not self.validate():
            if self.amount_spin.value() <= 0:
                QMessageBox.warning(self, _t("common.error"), _t("adjust_balance.invalid_amount"))
            else:
                QMessageBox.warning(self, _t("common.error"), _t("adjust_balance.reason_required"))
            return

        current_user = AuthService.get_current_user()
        user_id = current_user.id if current_user else 1

        delta = self.calculate_delta()
        note = self.reason_edit.text().strip()

        try:
            CustomerCreditService.record_adjustment(
                customer_id=self.customer.id,
                amount=delta,
                note=note,
                user_id=user_id,
            )
            self.accept()
        except Exception as e:
            logger.error("Failed to record balance adjustment: %s", e)
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
