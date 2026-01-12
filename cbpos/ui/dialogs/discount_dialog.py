from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QDoubleSpinBox,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QGridLayout,
    QMessageBox,
)
from PyQt6.QtCore import Qt


class DiscountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply Discount")
        self.setFixedSize(400, 350)
        self.setFixedSize(400, 350)
        self.setObjectName("DiscountDialog")

        self.discount_type = "PERCENTAGE"
        self.discount_value = 0.0

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # 1. Discount Type Selection
        type_layout = QHBoxLayout()
        self.type_group = QButtonGroup(self)

        self.rb_percent = QRadioButton("Percentage (%)")
        self.rb_percent.setChecked(True)
        self.rb_percent.setObjectName("RbPercent")
        self.type_group.addButton(self.rb_percent)

        self.rb_fixed = QRadioButton("Fixed Amount (Rs)")
        self.rb_fixed.setObjectName("RbFixed")
        self.type_group.addButton(self.rb_fixed)

        type_layout.addWidget(self.rb_percent)
        type_layout.addWidget(self.rb_fixed)
        layout.addLayout(type_layout)

        self.type_group.buttonClicked.connect(self.on_type_changed)

        # 2. Value Input
        self.spin_value = QDoubleSpinBox()
        self.spin_value.setRange(0, 999999)
        self.spin_value.setDecimals(2)
        self.spin_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_value.setObjectName("DiscountValueInput")
        layout.addWidget(self.spin_value)

        # 3. Presets
        self.presets_layout = QGridLayout()
        presets = [5, 10, 15, 20, 25, 50]

        row = 0
        col = 0
        for p in presets:
            btn = QPushButton(f"{p}%")
            btn.setFixedSize(80, 50)
            btn.setProperty("class", "PresetBtn")
            btn.clicked.connect(lambda checked, val=p: self.spin_value.setValue(val))
            self.presets_layout.addWidget(btn, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        layout.addLayout(self.presets_layout)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(50)
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.clicked.connect(self.reject)

        btn_apply = QPushButton("Apply Discount")
        btn_apply.setFixedHeight(50)
        btn_apply.setObjectName("BtnApplyDiscount")
        btn_apply.clicked.connect(self.accept)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)
        layout.addLayout(btn_layout)

    def on_type_changed(self, button):
        if button == self.rb_percent:
            self.discount_type = "PERCENTAGE"
            self.spin_value.setSuffix("%")
            self.presets_layout.setEnabled(True)
        else:
            self.discount_type = "FIXED"
            self.spin_value.setSuffix("")
            self.presets_layout.setEnabled(False)  # Disable presets for fixed amount

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
