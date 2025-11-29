from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QDoubleSpinBox,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QGridLayout,
)
from PyQt6.QtCore import Qt


class DiscountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply Discount")
        self.setFixedSize(400, 350)
        self.setStyleSheet("background-color: #001F3F; color: white;")

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
        self.rb_percent.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.type_group.addButton(self.rb_percent)

        self.rb_fixed = QRadioButton("Fixed Amount (Rs)")
        self.rb_fixed.setStyleSheet("font-size: 16px; font-weight: bold;")
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
        self.spin_value.setStyleSheet(
            """
            QDoubleSpinBox {
                font-size: 32px;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #00BCEB;
                border-radius: 5px;
                background-color: #003366;
                color: white;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                width: 0px;
            }
        """
        )
        layout.addWidget(self.spin_value)

        # 3. Presets
        self.presets_layout = QGridLayout()
        presets = [5, 10, 15, 20, 25, 50]

        row = 0
        col = 0
        for p in presets:
            btn = QPushButton(f"{p}%")
            btn.setFixedSize(80, 50)
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #0074D9;
                    color: white;
                    font-weight: bold;
                    font-size: 16px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #005bb5;
                }
            """
            )
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
        btn_cancel.setStyleSheet(
            """
            background-color: #FF4136;
            color: white;
            font-weight: bold;
            font-size: 16px;
            border-radius: 5px;
        """
        )
        btn_cancel.clicked.connect(self.reject)

        btn_apply = QPushButton("Apply Discount")
        btn_apply.setFixedHeight(50)
        btn_apply.setStyleSheet(
            """
            background-color: #39FF14;
            color: black;
            font-weight: bold;
            font-size: 16px;
            border-radius: 5px;
        """
        )
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
