from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class DiscountDialog(QDialog):
    """Dialog for entering a percentage or fixed-amount discount, with live preview against the original amount."""

    def __init__(self, parent=None, original_amount: Decimal = Decimal("0.00")):
        """Initialize the dialog with the amount the discount will be applied against."""
        super().__init__(parent)
        self.setWindowTitle(_t("discount.title"))
        # Fixed WIDTH only -- a hardcoded fixed HEIGHT (previously 440)
        # has no slack for font-metric differences across systems/fonts,
        # and this dialog's content is already right at that edge: on a
        # system whose fonts render even slightly taller, the content
        # stops fitting and QGridLayout silently collapses the preset
        # buttons' vertical spacing to 0 to force everything into the
        # fixed height, visibly merging the two preset rows together.
        # Letting height follow the layout's real sizeHint means it is
        # always exactly tall enough, on any system, font, or language
        # (including a future Sinhala/Tamil translation of this dialog's
        # own labels, which may need more vertical room than English).
        self.setFixedWidth(420)
        self.setObjectName("DiscountDialog")

        self.discount_type = "PERCENTAGE"
        self.discount_value = 0.0
        self.original_amount = original_amount

        self.init_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def init_ui(self):
        """Build the discount type toggle, value input, presets, and preview label."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setProperty("class", "dialog-title")
        layout.addWidget(self.title_label)

        # Discount Type Selection — styled as segmented control
        type_frame = QFrame()
        type_frame.setObjectName("DiscountTypeFrame")
        type_layout = QHBoxLayout(type_frame)
        type_layout.setContentsMargins(4, 4, 4, 4)
        type_layout.setSpacing(4)

        self.type_group = QButtonGroup(self)

        # Checkable QPushButtons instead of QRadioButtons -- a radio
        # button's indicator+text always render left-anchored inside
        # whatever width the layout gives it, leaving a lopsided gap of
        # empty space on the right of each segment. QPushButton centers
        # its text by default, which is what an actual segmented control
        # needs; this is also the same checkable-QPushButton pattern
        # already used for tab-like toggles elsewhere in this app (e.g.
        # sale_history_dialog.py, sales_view.py's quick filters).
        self.rb_percent = QPushButton("")
        self.rb_percent.setCheckable(True)
        self.rb_percent.setChecked(True)
        self.rb_percent.setObjectName("RbPercent")
        self.rb_percent.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.type_group.addButton(self.rb_percent)

        self.rb_fixed = QPushButton("")
        self.rb_fixed.setCheckable(True)
        self.rb_fixed.setObjectName("RbFixed")
        self.rb_fixed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.type_group.addButton(self.rb_fixed)

        # Equal stretch so both segments split the frame 50/50 regardless
        # of "Percentage (%)" and "Fixed Amount (Rs)" having different
        # text lengths.
        type_layout.addWidget(self.rb_percent, 1)
        type_layout.addWidget(self.rb_fixed, 1)
        layout.addWidget(type_frame)

        self.type_group.buttonClicked.connect(self.on_type_changed)

        # Value Input
        self.spin_value = QDoubleSpinBox()
        self.spin_value.setRange(0, 999999)
        self.spin_value.setDecimals(2)
        self.spin_value.setSuffix("%")
        self.spin_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_value.setObjectName("DiscountValueInput")
        layout.addWidget(self.spin_value)

        # Presets
        self.presets_layout = QGridLayout()
        self.presets_layout.setSpacing(8)
        presets = [5, 10, 15, 20, 25, 50]

        row = 0
        col = 0
        for p in presets:
            btn = QPushButton(f"{p}%")
            btn.setFixedHeight(44)
            btn.setProperty("class", "PresetBtn")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda checked, val=p: self.spin_value.setValue(val))
            self.presets_layout.addWidget(btn, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        layout.addLayout(self.presets_layout)

        # Live preview label
        self.lbl_preview = QLabel("")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setProperty("class", "muted")
        self.lbl_preview.setWordWrap(True)
        layout.addWidget(self.lbl_preview)

        # Connect signals for live preview
        self.spin_value.valueChanged.connect(self._update_preview)
        self.rb_percent.toggled.connect(self._update_preview)
        self.rb_fixed.toggled.connect(self._update_preview)
        self._update_preview()

        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_cancel = QPushButton("")
        self.btn_cancel.setFixedHeight(48)
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_apply = QPushButton("")
        self.btn_apply.setFixedHeight(48)
        self.btn_apply.setObjectName("BtnApplyDiscount")
        self.btn_apply.setProperty("class", "primary")
        self.btn_apply.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("discount.title"))
        self.title_label.setText(_t("discount.title"))
        self.rb_percent.setText(_t("discount.type_percentage"))
        self.rb_percent.setToolTip(_t("discount.tooltip_percentage"))
        self.rb_fixed.setText(_t("discount.type_fixed"))
        self.rb_fixed.setToolTip(_t("discount.tooltip_fixed"))
        self.btn_cancel.setText(_t("discount.btn_cancel"))
        self.btn_apply.setText(_t("discount.btn_apply"))

    def _update_preview(self) -> None:
        """Update the live preview label with the discounted result."""
        if self.original_amount <= 0:
            self.lbl_preview.setText("")
            return

        value = Decimal(str(self.spin_value.value()))
        original = self.original_amount

        if self.rb_percent.isChecked():
            discount_amt = original * value / Decimal("100")
        else:
            discount_amt = value

        after = max(original - discount_amt, Decimal("0.00"))
        orig_str = f"{original:,.2f}"
        disc_str = f"{after:,.2f}"
        self.lbl_preview.setText(_t("discount.preview", original=orig_str, discounted=disc_str))

    def on_type_changed(self, button):
        """Switch the value input's range/suffix and preset buttons between percentage and fixed-amount mode."""
        if button == self.rb_percent:
            self.discount_type = "PERCENTAGE"
            self.spin_value.setSuffix("%")
            self.spin_value.setRange(0, 100)
            # Enable preset buttons
            for i in range(self.presets_layout.count()):
                widget = self.presets_layout.itemAt(i).widget()
                if widget:
                    widget.setEnabled(True)
        else:
            self.discount_type = "FIXED"
            self.spin_value.setSuffix("")
            self.spin_value.setRange(0, 999999)
            # Disable preset buttons for fixed amount
            for i in range(self.presets_layout.count()):
                widget = self.presets_layout.itemAt(i).widget()
                if widget:
                    widget.setEnabled(False)

    def showEvent(self, event):
        """Focus and pre-select the value field so a cashier can start
        typing a discount immediately -- this app is keyboard-first by
        product principle, and this dialog's entire job is entering one
        number quickly. Matches the same pattern already used by
        ManagerOverrideDialog for its PIN field.
        """
        super().showEvent(event)
        self.spin_value.setFocus()
        self.spin_value.selectAll()

    def get_data(self):
        """Return the chosen discount type ("PERCENTAGE" or "FIXED") and its value."""
        return self.discount_type, self.spin_value.value()

    def accept(self):
        """Reject a zero/negative discount value, otherwise accept the dialog."""
        if self.spin_value.value() <= 0:
            QMessageBox.warning(
                self,
                _t("discount.invalid_title"),
                _t("discount.invalid_message"),
            )
            return
        super().accept()
