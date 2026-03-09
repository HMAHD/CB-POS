from decimal import Decimal

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QDoubleSpinBox,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QGridLayout,
    QLabel,
    QFrame,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from cbpos.i18n import _t


class DiscountDialog(QDialog):
    def __init__(self, parent=None, original_amount: Decimal = Decimal("0.00")):
        super().__init__(parent)
        self.setWindowTitle(_t("discount.title"))
        self.setFixedSize(420, 440)
        self.setObjectName("DiscountDialog")

        self.discount_type = "PERCENTAGE"
        self.discount_value = 0.0
        self.original_amount = original_amount

        self.init_ui()

    def init_ui(self):
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

        self.rb_percent = QRadioButton("")
        self.rb_percent.setChecked(True)
        self.rb_percent.setObjectName("RbPercent")
        self.type_group.addButton(self.rb_percent)

        self.rb_fixed = QRadioButton("")
        self.rb_fixed.setObjectName("RbFixed")
        self.type_group.addButton(self.rb_fixed)

        type_layout.addWidget(self.rb_percent)
        type_layout.addWidget(self.rb_fixed)
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
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_apply = QPushButton("")
        self.btn_apply.setFixedHeight(48)
        self.btn_apply.setObjectName("BtnApplyDiscount")
        self.btn_apply.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_apply)
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
        orig_str = "{:,.2f}".format(original)
        disc_str = "{:,.2f}".format(after)
        self.lbl_preview.setText(_t("discount.preview", original=orig_str, discounted=disc_str))

    def on_type_changed(self, button):
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

    def get_data(self):
        return self.discount_type, self.spin_value.value()

    def accept(self):
        if self.spin_value.value() <= 0:
            QMessageBox.warning(
                self,
                _t("discount.invalid_title"),
                _t("discount.invalid_message"),
            )
            return
        super().accept()
