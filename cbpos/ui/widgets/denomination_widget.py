from decimal import Decimal
from typing import List

from PyQt6.QtWidgets import (
    QWidget,
    QGridLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
)
from PyQt6.QtCore import pyqtSignal

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t


class DenominationWidget(QWidget):
    """Widget for blind cash counting.

    The list of denominations is read from the configuration service.
    It can also be passed explicitly for testing.
    """

    total_changed = pyqtSignal(Decimal)

    def __init__(self, denominations: List[int] = None, parent=None):
        super().__init__(parent)

        # 1. Load denominations (Sri Lankan currency by default)
        if denominations is None:
            cfg = ConfigService.get_all()
            denominations = cfg.get(
                "currency_denominations",
                [5000, 1000, 500, 100, 50, 20],
            )
        self.denominations = sorted(denominations, reverse=True)

        self._current_total = Decimal(0)
        self.counts: dict[int, QSpinBox | QDoubleSpinBox] = {}

        self._build_ui()
        self.calculate_total()

    def _build_ui(self):
        layout = QGridLayout(self)

        for idx, denom in enumerate(self.denominations):
            row, col = divmod(idx, 2)  # two columns
            lbl = QLabel("{:,}".format(denom))
            spin = QSpinBox() if denom >= 20 else QDoubleSpinBox()
            spin.setRange(0, 9999)
            spin.setSingleStep(1 if denom >= 20 else 0.01)
            spin.setProperty("lbl_total", QLabel())  # placeholder for row total
            spin.valueChanged.connect(self.calculate_total)

            self.counts[denom] = spin

            layout.addWidget(lbl, row, col * 3)
            layout.addWidget(spin, row, col * 3 + 1)
            layout.addWidget(spin.property("lbl_total"), row, col * 3 + 2)

        # Grand total label (spans both columns)
        self.lbl_grand_total = QLabel("0.00")
        # Place it below the last row of denominations
        total_row = (len(self.denominations) + 1) // 2
        layout.addWidget(QLabel(_t("denomination.grand_total")), total_row, 0, 1, 2)
        layout.addWidget(self.lbl_grand_total, total_row, 2, 1, 4)

        # Coins are assumed to be covered by the denominations list (e.g. 10, 5, 2, 1)
        # or handled via configuration.

    def calculate_total(self):
        total = Decimal(0)

        for denom, spin in self.counts.items():
            count = Decimal(str(spin.value()))
            subtotal = count * Decimal(denom)
            total += subtotal

            # update per-row total label
            lbl = spin.property("lbl_total")
            if lbl:
                lbl.setText("{:,.2f}".format(subtotal))

        self._current_total = total
        self.lbl_grand_total.setText("{:,.2f}".format(total))
        self.total_changed.emit(total)

    def get_total(self) -> Decimal:
        return self._current_total
