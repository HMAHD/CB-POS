import weakref
from decimal import Decimal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback


class DenominationWidget(QWidget):
    """Widget for blind cash counting.

    The list of denominations is read from the configuration service.
    It can also be passed explicitly for testing.
    """

    total_changed = pyqtSignal(Decimal)

    def __init__(self, denominations: list[int] = None, parent=None):
        """Build the spin-box grid for each denomination and compute the initial total.

        Args:
            denominations: Currency denominations to count; defaults to the
                configured ``currency_denominations`` (Sri Lankan notes/coins).
            parent: Optional parent widget.
        """
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
        self._row_totals: dict[int, QLabel] = {}

        self._build_ui()
        self.calculate_total()

    def _build_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        for idx, denom in enumerate(self.denominations):
            row, col = divmod(idx, 2)  # two columns
            lbl = QLabel(f"{denom:,}")
            lbl.setObjectName("DenomLabel")
            spin = QSpinBox() if denom >= 20 else QDoubleSpinBox()
            spin.setObjectName("DenomSpin")
            spin.setRange(0, 9999)
            spin.setSingleStep(1 if denom >= 20 else 0.01)
            spin.setMinimumHeight(36)
            lbl_row_total = QLabel()
            lbl_row_total.setObjectName("DenomRowTotal")
            lbl_row_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl_row_total.setMinimumWidth(80)
            spin.valueChanged.connect(self.calculate_total)

            self.counts[denom] = spin
            self._row_totals[denom] = lbl_row_total

            layout.addWidget(lbl, row, col * 3)
            layout.addWidget(spin, row, col * 3 + 1)
            layout.addWidget(lbl_row_total, row, col * 3 + 2)

        # Grand total label (spans both columns)
        self.lbl_grand_total = QLabel("0.00")
        self.lbl_grand_total.setObjectName("DenomGrandTotalValue")
        self.lbl_grand_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # Place it below the last row of denominations
        total_row = (len(self.denominations) + 1) // 2
        self._lbl_grand_total_label = QLabel(_t("denomination.grand_total"))
        self._lbl_grand_total_label.setObjectName("DenomGrandTotalLabel")
        layout.addWidget(self._lbl_grand_total_label, total_row, 0, 1, 2)
        layout.setRowMinimumHeight(total_row, 44)

        register_language_callback(self._retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        def _unregister():
            widget = self_ref()
            if widget is not None:
                unregister_language_callback(widget._retranslate_ui)

        self.destroyed.connect(_unregister)
        layout.addWidget(self.lbl_grand_total, total_row, 2, 1, 4)

        # Coins are assumed to be covered by the denominations list (e.g. 10, 5, 2, 1)
        # or handled via configuration.

    def _retranslate_ui(self) -> None:
        self._lbl_grand_total_label.setText(_t("denomination.grand_total"))

    def calculate_total(self):
        """Recompute the grand total from all spin-box counts, update the
        per-row and grand total labels, and emit ``total_changed``.
        """
        total = Decimal(0)

        for denom, spin in self.counts.items():
            count = Decimal(str(spin.value()))
            subtotal = count * Decimal(denom)
            total += subtotal

            # update per-row total label
            self._row_totals[denom].setText(f"{subtotal:,.2f}")

        self._current_total = total
        self.lbl_grand_total.setText(f"{total:,.2f}")
        self.total_changed.emit(total)

    def get_total(self) -> Decimal:
        """Return the last-computed total."""
        return self._current_total
