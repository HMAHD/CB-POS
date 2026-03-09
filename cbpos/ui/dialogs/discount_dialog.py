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


class DiscountDialog(QDialog):
    def __init__(self, parent=None, original_amount: Decimal = Decimal("0.00")):
        super().__init__(parent)
        self.setWindowTitle("Apply Discount")
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
        title = QLabel("Apply Discount")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Discount Type Selection — styled as segmented control
        type_frame = QFrame()
        type_frame.setObjectName("DiscountTypeFrame")
        type_layout = QHBoxLayout(type_frame)
        type_layout.setContentsMargins(4, 4, 4, 4)
        type_layout.setSpacing(4)

        self.type_group = QButtonGroup(self)

        self.rb_percent = QRadioButton("Percentage (%)")
        self.rb_percent.setChecked(True)
        self.rb_percent.setObjectName("RbPercent")
        self.rb_percent.setToolTip("Percentage: e.g., 10% off any price")
        self.type_group.addButton(self.rb_percent)

        self.rb_fixed = QRadioButton("Fixed Amount (Rs)")
        self.rb_fixed.setObjectName("RbFixed")
        self.rb_fixed.setToolTip("Fixed: e.g., Remove Rs 500 from total")
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

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(48)
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.clicked.connect(self.reject)

        btn_apply = QPushButton("Apply Discount")
        btn_apply.setFixedHeight(48)
        btn_apply.setObjectName("BtnApplyDiscount")
        btn_apply.clicked.connect(self.accept)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)
        layout.addLayout(btn_layout)

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
        self.lbl_preview.setText(f"Original: Rs {original:,.2f}  →  After discount: Rs {after:,.2f}")  # noqa: E231

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
                "Invalid Input",
                "Please enter a valid discount value.",
            )
            return
        super().accept()
