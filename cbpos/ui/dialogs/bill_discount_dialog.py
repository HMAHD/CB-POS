"""Dialog for entering a whole-bill discount (% or amount) with live preview (#813)."""

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.utils.formatters import format_currency
from cbpos.core.utils.money import round_money
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class BillDiscountDialog(QDialog):
    """Dialog for applying a bill-level discount (% or fixed amount) to the entire cart."""

    def __init__(
        self,
        parent=None,
        current_subtotal: Decimal = Decimal("0.00"),
        current_type: str = "NONE",
        current_value: Decimal = Decimal("0.00"),
        max_discount_pct: Decimal = Decimal("0.00"),
    ):
        """Build the bill discount dialog.

        Args:
            parent: Optional parent widget.
            current_subtotal: Total cart amount before bill discount (after line discounts).
            current_type: Current discount type ("PERCENTAGE", "FIXED", or "NONE").
            current_value: Current discount value.
            max_discount_pct: Maximum allowed discount percentage before manager override.
        """
        super().__init__(parent)
        self.setObjectName("BillDiscountDialog")
        self.setFixedWidth(420)

        self.current_subtotal = current_subtotal
        self.max_discount_pct = max_discount_pct

        if current_type == "FIXED":
            self.discount_type = "FIXED"
            init_val = float(current_value)
        elif current_type == "PERCENTAGE":
            self.discount_type = "PERCENTAGE"
            init_val = float(current_value)
        else:
            self.discount_type = "PERCENTAGE"
            init_val = 0.0

        self.discount_value = Decimal(str(init_val))
        self._had_existing_discount = current_type != "NONE" and current_value > Decimal("0.00")

        self.init_ui(init_val)
        install_wheel_guard(self)

    def init_ui(self, init_val: float) -> None:
        """Lay out segmented toggle, value input, preview, and buttons."""
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        self.title_label = QLabel(_t("bill_discount.title"))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setProperty("class", "dialog-title")
        layout.addWidget(self.title_label)

        # Segmented type toggle (% vs Amount)
        type_frame = QFrame()
        type_frame.setObjectName("DiscountTypeFrame")
        type_layout = QHBoxLayout(type_frame)
        type_layout.setContentsMargins(4, 4, 4, 4)
        type_layout.setSpacing(4)

        self.type_group = QButtonGroup(self)

        self.rb_percent = QPushButton(_t("bill_discount.percent"))
        self.rb_percent.setCheckable(True)
        self.rb_percent.setObjectName("RbPercent")
        self.rb_percent.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.type_group.addButton(self.rb_percent)

        self.rb_fixed = QPushButton(_t("bill_discount.amount"))
        self.rb_fixed.setCheckable(True)
        self.rb_fixed.setObjectName("RbFixed")
        self.rb_fixed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.type_group.addButton(self.rb_fixed)

        if self.discount_type == "FIXED":
            self.rb_fixed.setChecked(True)
        else:
            self.rb_percent.setChecked(True)

        type_layout.addWidget(self.rb_percent, 1)
        type_layout.addWidget(self.rb_fixed, 1)
        layout.addWidget(type_frame)

        self.type_group.buttonClicked.connect(self._on_type_changed)

        # Value input
        self.spin_value = QDoubleSpinBox()
        self.spin_value.setDecimals(2)
        self.spin_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_value.setObjectName("BillDiscountValueInput")

        if self.discount_type == "PERCENTAGE":
            self.spin_value.setRange(0, 100)
            self.spin_value.setSuffix("%")
        else:
            self.spin_value.setRange(0, 999999)
            self.spin_value.setSuffix("")

        self.spin_value.setValue(init_val)
        layout.addWidget(self.spin_value)

        # Live preview label
        self.lbl_preview = QLabel("")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setProperty("class", "muted")
        self.lbl_preview.setWordWrap(True)
        layout.addWidget(self.lbl_preview)

        # Over cap warning label
        self.lbl_cap_warning = QLabel("")
        self.lbl_cap_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cap_warning.setProperty("class", "warning")
        self.lbl_cap_warning.setWordWrap(True)
        self.lbl_cap_warning.setVisible(False)
        layout.addWidget(self.lbl_cap_warning)

        # Remove discount button (if one already exists)
        self.btn_remove = QPushButton(_t("bill_discount.remove"))
        self.btn_remove.setObjectName("BtnRemoveDiscount")
        self.btn_remove.setProperty("class", "danger")
        self.btn_remove.setFixedHeight(36)
        self.btn_remove.clicked.connect(self._on_remove_clicked)
        self.btn_remove.setVisible(self._had_existing_discount)
        layout.addWidget(self.btn_remove)

        layout.addStretch()

        # Footer: [Apply] [Cancel]
        footer_layout, self.btn_apply, self.btn_cancel = make_dialog_footer(
            primary_key="discount.btn_apply",
            on_primary=self.accept,
            cancel_key="discount.btn_cancel",
            on_cancel=self.reject,
            primary_object_name="BtnApplyDiscount",
            cancel_object_name="BtnCancel",
        )
        layout.addLayout(footer_layout)

        # Connect live updates
        self.spin_value.valueChanged.connect(self._update_preview)
        self.rb_percent.toggled.connect(self._update_preview)
        self.rb_fixed.toggled.connect(self._update_preview)

        # Keyboard shortcuts: Alt+P for percent, Alt+A for amount, Tab to toggle
        self._shortcut_pct = QShortcut(QKeySequence("Alt+P"), self)
        self._shortcut_pct.activated.connect(lambda: self.rb_percent.click())
        self._shortcut_amt = QShortcut(QKeySequence("Alt+A"), self)
        self._shortcut_amt.activated.connect(lambda: self.rb_fixed.click())

        self.retranslate_ui()
        self._update_preview()

    def retranslate_ui(self) -> None:
        """Translate UI labels."""
        self.setWindowTitle(_t("bill_discount.title"))
        self.title_label.setText(_t("bill_discount.title"))
        self.rb_percent.setText(_t("bill_discount.percent"))
        self.rb_fixed.setText(_t("bill_discount.amount"))
        self.btn_remove.setText(_t("bill_discount.remove"))
        if self.btn_apply:
            self.btn_apply.setText(_t("discount.btn_apply"))
        if self.btn_cancel:
            self.btn_cancel.setText(_t("discount.btn_cancel"))

    def _on_type_changed(self, button: QPushButton) -> None:
        """Switch between percentage and fixed amount modes."""
        if button == self.rb_percent:
            self.discount_type = "PERCENTAGE"
            self.spin_value.setSuffix("%")
            self.spin_value.setRange(0, 100)
        else:
            self.discount_type = "FIXED"
            self.spin_value.setSuffix("")
            self.spin_value.setRange(0, 999999)
        self._update_preview()

    def _on_remove_clicked(self) -> None:
        """Remove discount and accept dialog."""
        self.discount_type = "NONE"
        self.discount_value = Decimal("0.00")
        self.accept()

    def _update_preview(self) -> None:
        """Update live preview and cap warning."""
        subtotal = self.current_subtotal
        val = Decimal(str(self.spin_value.value()))

        if self.rb_percent.isChecked():
            disc_amount = round_money(subtotal * (val / Decimal("100")))
            eff_pct = val
        else:
            disc_amount = round_money(val)
            eff_pct = (disc_amount / subtotal * Decimal("100")) if subtotal > Decimal("0") else Decimal("0")

        disc_amount = min(disc_amount, subtotal)
        after = max(subtotal - disc_amount, Decimal("0.00"))

        self.lbl_preview.setText(
            _t(
                "bill_discount.preview",
                before=format_currency(subtotal),
                after=format_currency(after),
                discount=format_currency(disc_amount),
            )
        )

        # Check cap
        if self.max_discount_pct > Decimal("0") and eff_pct > self.max_discount_pct:
            self.lbl_cap_warning.setText(_t("bill_discount.over_cap", cap=str(self.max_discount_pct)))
            self.lbl_cap_warning.setVisible(True)
        else:
            self.lbl_cap_warning.setVisible(False)

    def showEvent(self, event) -> None:
        """Focus and select value field on open."""
        super().showEvent(event)
        self.spin_value.setFocus()
        self.spin_value.selectAll()

    def get_data(self) -> tuple[str, Decimal]:
        """Return the chosen discount type and value."""
        if self.discount_type == "NONE":
            return "NONE", Decimal("0.00")
        return self.discount_type, Decimal(str(self.spin_value.value()))
