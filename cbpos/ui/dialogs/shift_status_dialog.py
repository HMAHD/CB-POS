from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QPushButton, QVBoxLayout

from cbpos.core.services.shift_service import ShiftService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t


class ShiftStatusDialog(QDialog):
    """Read-only mid-shift snapshot (X-Read): sales so far, expected cash, transaction
    count. No counted-cash input, no closing action -- purely informational, so a
    cashier or manager can check running totals without risking an accidental shift close.
    """

    def __init__(self, shift_id: int, parent=None):
        """Build the dialog and populate it from `ShiftService.get_shift_summary(shift_id)`."""
        super().__init__(parent)
        self.setWindowTitle(_t("shift_status.title"))
        self.setFixedSize(450, 420)

        summary = ShiftService().get_shift_summary(shift_id)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        rows = [
            ("shift_status.starting_cash", summary.get("starting_cash")),
            ("shift_status.cash_sales", summary.get("cash_sales")),
            ("shift_status.card_sales", summary.get("card_sales")),
            ("shift_status.credit_sales", summary.get("credit_sales")),
            ("shift_status.qr_mobile_sales", summary.get("qr_mobile_sales")),
            ("shift_status.cheque_sales", summary.get("cheque_sales")),
            ("shift_status.transfer_sales", summary.get("transfer_sales")),
            ("shift_status.cash_in", summary.get("cash_in")),
            ("shift_status.cash_out", summary.get("cash_out")),
            ("shift_status.expected_cash", summary.get("expected_cash")),
        ]
        for key, value in rows:
            form.addRow(_t(key), QLabel(format_currency(value or 0)))

        form.addRow(_t("shift_status.txn_count"), QLabel(str(summary.get("txn_count") or 0)))
        form.addRow(_t("shift_status.void_count"), QLabel(str(summary.get("void_count") or 0)))

        layout.addLayout(form)

        btn_close = QPushButton(_t("common.close"))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
