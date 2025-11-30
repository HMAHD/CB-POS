from PyQt6.QtWidgets import (
    QWidget,
    QGridLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from decimal import Decimal


class DenominationWidget(QWidget):
    total_changed = pyqtSignal(Decimal)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.denominations = [5000, 1000, 500, 100, 50, 20]
        self.counts = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Grid for Notes
        grid = QGridLayout()
        grid.setVerticalSpacing(10)
        grid.setHorizontalSpacing(20)

        row = 0
        row = 0

        # Add headers
        grid.addWidget(QLabel("Denomination"), 0, 0)
        grid.addWidget(QLabel("Count"), 0, 1)
        grid.addWidget(QLabel("Total"), 0, 2)

        grid.addWidget(QLabel("Denomination"), 0, 4)
        grid.addWidget(QLabel("Count"), 0, 5)
        grid.addWidget(QLabel("Total"), 0, 6)

        # Vertical divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        grid.addWidget(line, 1, 3, 4, 1)

        row = 1
        for denom in self.denominations:
            # Label
            lbl = QLabel(f"{denom}")
            lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            # SpinBox
            spin = QSpinBox()
            spin.setRange(0, 10000)
            spin.setFixedWidth(80)
            spin.valueChanged.connect(self.calculate_total)
            self.counts[denom] = spin

            # Row Total
            lbl_total = QLabel("0.00")
            lbl_total.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            lbl_total.setStyleSheet("color: #00BCEB;")

            # Store reference to update later
            spin.setProperty("lbl_total", lbl_total)
            spin.setProperty("denom", denom)

            # Layout logic (2 columns)
            c = 0 if row <= 3 else 4
            r = row if row <= 3 else row - 3

            grid.addWidget(lbl, r, c)
            grid.addWidget(spin, r, c + 1)
            grid.addWidget(lbl_total, r, c + 2)

            row += 1

        layout.addLayout(grid)

        # Coins Section
        coins_frame = QFrame()
        coins_frame.setStyleSheet(
            "background-color: #2D2D30; border-radius: 5px; padding: 5px;"
        )
        coins_layout = QHBoxLayout(coins_frame)

        lbl_coins = QLabel("Coins / Other:")
        lbl_coins.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.spin_coins = QDoubleSpinBox()
        self.spin_coins.setRange(0, 100000)
        self.spin_coins.setDecimals(2)
        self.spin_coins.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_coins.valueChanged.connect(self.calculate_total)

        coins_layout.addWidget(lbl_coins)
        coins_layout.addWidget(self.spin_coins)

        layout.addWidget(coins_frame)

        # Grand Total Display
        total_frame = QFrame()
        total_frame.setStyleSheet("border-top: 1px solid #555; margin-top: 10px;")
        total_layout = QHBoxLayout(total_frame)

        lbl_grand = QLabel("Total Cash:")
        lbl_grand.setStyleSheet("font-size: 16px; color: #AAAAAA;")

        self.lbl_grand_total = QLabel("0.00")
        self.lbl_grand_total.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #39FF14;"
        )
        self.lbl_grand_total.setAlignment(Qt.AlignmentFlag.AlignRight)

        total_layout.addWidget(lbl_grand)
        total_layout.addStretch()
        total_layout.addWidget(self.lbl_grand_total)

        layout.addWidget(total_frame)

    def calculate_total(self):
        total = Decimal(0)

        # Notes
        for denom, spin in self.counts.items():
            count = spin.value()
            subtotal = Decimal(count) * Decimal(denom)
            total += subtotal

            # Update row label
            lbl = spin.property("lbl_total")
            if lbl:
                lbl.setText("{:,.2f}".format(subtotal))

        # Coins
        total += Decimal(str(self.spin_coins.value()))

        self.lbl_grand_total.setText("{:,.2f}".format(total))
        self.total_changed.emit(total)

    def get_total(self) -> Decimal:
        return Decimal(self.lbl_grand_total.text().replace(",", ""))
