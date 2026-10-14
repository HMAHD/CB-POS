"""One place for everything about the cashier's open shift (#605)."""

import contextlib
import logging
from decimal import Decimal
from typing import Any

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.constants.permissions import Permissions
from cbpos.core.services.printer_service import PrinterService
from cbpos.core.services.shift_service import ShiftService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.cash_movement_dialog import CashMovementDialog
from cbpos.ui.dialogs.shift_closing_dialog import ShiftClosingDialog
from cbpos.ui.resources.icons import Icons

logger = logging.getLogger(__name__)

# (summary key, i18n key) -- the X-read figures, in display order.
_MONEY_ROWS = [
    ("starting_cash", "shift_status.starting_cash"),
    ("cash_sales", "shift_status.cash_sales"),
    ("card_sales", "shift_status.card_sales"),
    ("credit_sales", "shift_status.credit_sales"),
    ("qr_mobile_sales", "shift_status.qr_mobile_sales"),
    ("cheque_sales", "shift_status.cheque_sales"),
    ("transfer_sales", "shift_status.transfer_sales"),
    ("cash_in", "shift_status.cash_in"),
    ("cash_out", "shift_status.cash_out"),
    ("expected_cash", "shift_status.expected_cash"),
]
_COUNT_ROWS = [
    ("txn_count", "shift_status.txn_count"),
    ("void_count", "shift_status.void_count"),
]


class ShiftManagementDialog(QDialog):
    """The cashier's open shift: X-read figures, Cash In / Cash Out, and End Shift.

    Opening it never changes the shift. Cash In / Cash Out record a
    ``CashMovement`` through ``ShiftService`` and refresh the figures, so the
    expected cash (and the Z-read at close) includes them. End Shift runs the
    existing closing wizard; ``shift_ended`` is True once it completes, so the
    caller can log the cashier out.
    """

    def __init__(self, shift_id: int, user_id: int, parent=None):
        """Build the dialog and load the current figures for ``shift_id``.

        Args:
            shift_id: The open shift to show.
            user_id: The cashier recording cash movements.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("ShiftManagementDialog")
        self.shift_id = shift_id
        self.user_id = user_id
        self.shift_ended = False
        self.value_labels: dict[str, QLabel] = {}
        self._summary: dict[str, Any] = {}

        self._init_ui()
        self.retranslate_ui()
        self.refresh()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        layout.addWidget(self.lbl_title)

        self.lbl_started = QLabel()
        self.lbl_started.setProperty("class", "muted")
        layout.addWidget(self.lbl_started)

        self.lbl_figures = QLabel()
        self.lbl_figures.setObjectName("ShiftSectionTitle")
        layout.addWidget(self.lbl_figures)

        self._form = QFormLayout()
        self._form.setHorizontalSpacing(24)
        self._form.setVerticalSpacing(6)
        self._row_labels: dict[str, QLabel] = {}
        for key, _ in _MONEY_ROWS + _COUNT_ROWS:
            name = QLabel()
            value = QLabel()
            if key == "expected_cash":
                name.setObjectName("ShiftExpectedCashLabel")
                value.setObjectName("ShiftExpectedCash")
            self._row_labels[key] = name
            self.value_labels[key] = value
            self._form.addRow(name, value)
        layout.addLayout(self._form)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("ShiftDivider")
        layout.addWidget(line)

        # Cash In / Cash Out -- record money put in or taken out of the drawer
        cash_row = QHBoxLayout()
        cash_row.setSpacing(10)
        self.btn_cash_in = QPushButton()
        self.btn_cash_in.setProperty("class", "secondary")
        self.btn_cash_in.setIcon(Icons.get("fa5s.plus-circle", "#2ECC40"))
        self.btn_cash_in.setMinimumHeight(44)
        self.btn_cash_in.clicked.connect(self._on_cash_in)
        cash_row.addWidget(self.btn_cash_in)

        self.btn_cash_out = QPushButton()
        self.btn_cash_out.setProperty("class", "secondary")
        self.btn_cash_out.setIcon(Icons.get("fa5s.minus-circle", "#FF851B"))
        self.btn_cash_out.setMinimumHeight(44)
        self.btn_cash_out.clicked.connect(self._on_cash_out)
        cash_row.addWidget(self.btn_cash_out)
        layout.addLayout(cash_row)

        # Print X-Read -- the figures above on paper, shift stays open (#682)
        self.btn_print_x_read = QPushButton()
        self.btn_print_x_read.setProperty("class", "secondary")
        self.btn_print_x_read.setIcon(Icons.get("fa5s.print", "#00BCEB"))
        self.btn_print_x_read.setMinimumHeight(44)
        self.btn_print_x_read.clicked.connect(self._print_x_read)
        layout.addWidget(self.btn_print_x_read)

        layout.addStretch()

        # End Shift sits apart from Close so it isn't hit by accident
        bottom_row = QHBoxLayout()
        self.btn_end_shift = QPushButton()
        self.btn_end_shift.setProperty("class", "danger")
        self.btn_end_shift.setMinimumHeight(44)
        self.btn_end_shift.clicked.connect(self._end_shift)
        bottom_row.addWidget(self.btn_end_shift)
        bottom_row.addStretch()

        self.btn_close = QPushButton()
        self.btn_close.setProperty("class", "secondary")
        self.btn_close.setMinimumHeight(44)
        self.btn_close.clicked.connect(self.reject)
        self.btn_close.setDefault(True)
        bottom_row.addWidget(self.btn_close)
        layout.addLayout(bottom_row)

        self.setMinimumWidth(460)

    def retranslate_ui(self) -> None:
        """Set all translatable text."""
        self.setWindowTitle(_t("shift_management.title"))
        self.lbl_title.setText(_t("shift_management.title"))
        self.lbl_figures.setText(_t("shift_management.figures_heading"))
        for key, text_key in _MONEY_ROWS + _COUNT_ROWS:
            self._row_labels[key].setText(_t(text_key))
        self.btn_cash_in.setText(_t("shift_management.cash_in"))
        self.btn_cash_out.setText(_t("shift_management.cash_out"))
        self.btn_print_x_read.setText(_t("shift_management.print_x_read"))
        self.btn_end_shift.setText(_t("shift_management.end_shift"))
        self.btn_close.setText(_t("common.close"))

    def refresh(self) -> None:
        """Reload the X-read figures from ``ShiftService``."""
        summary = ShiftService().get_shift_summary(self.shift_id)
        self._summary = summary
        for key, _ in _MONEY_ROWS:
            self.value_labels[key].setText(format_currency(summary.get(key) or Decimal(0)))
        for key, _ in _COUNT_ROWS:
            self.value_labels[key].setText(str(summary.get(key) or 0))
        start = summary.get("start_time")
        self.lbl_started.setText(
            _t("shift_management.started", time=start.strftime("%Y-%m-%d %H:%M"), user=summary.get("user_name", ""))
            if start
            else ""
        )

    def _print_x_read(self) -> None:
        """Print the current figures as an X-Read; report the printer's real outcome."""
        worker = PrintWorker.instance()
        self._disconnect_print_signals(worker)
        worker.job_completed.connect(self._on_x_read_printed)
        worker.error_occurred.connect(self._on_x_read_error)
        self.btn_print_x_read.setEnabled(False)
        try:
            PrinterService.print_shift_report(self._summary, x_read=True)
        except Exception as e:
            logger.error("X-Read could not be built: %s", e)
            self._on_x_read_error(str(e))

    def _disconnect_print_signals(self, worker: PrintWorker) -> None:
        with contextlib.suppress(TypeError):
            worker.job_completed.disconnect(self._on_x_read_printed)
        with contextlib.suppress(TypeError):
            worker.error_occurred.disconnect(self._on_x_read_error)

    def _on_x_read_printed(self) -> None:
        self._disconnect_print_signals(PrintWorker.instance())
        self.btn_print_x_read.setEnabled(True)
        QMessageBox.information(self, _t("common.success"), _t("shift_management.x_read_printed"))

    def _on_x_read_error(self, message: str) -> None:
        self._disconnect_print_signals(PrintWorker.instance())
        self.btn_print_x_read.setEnabled(True)
        logger.error("X-Read print failed: %s", message)
        QMessageBox.warning(self, _t("common.warning"), _t("shift_management.x_read_failed", error=message))

    def _on_cash_in(self) -> None:
        self._record_movement("IN")

    def _on_cash_out(self) -> None:
        self._record_movement("OUT")

    def _record_movement(self, movement_type: str) -> None:
        """Ask for an amount and reason, then record cash put in ("IN") or taken out ("OUT")."""
        from cbpos.core.utils import permission_helper

        if not permission_helper.check_permission_with_override(Permissions.CASH_OPEN_DRAWER, self):
            return

        dialog = CashMovementDialog(movement_type, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            ShiftService().record_cash_movement(
                self.shift_id, movement_type, dialog.amount, dialog.reason, self.user_id
            )
        except Exception as e:
            logger.error("Cash movement failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), _t("shift_management.movement_failed", error=str(e)))
            return
        self.refresh()

    def _end_shift(self) -> None:
        """Run the closing wizard; on success mark the shift ended and close."""
        dialog = ShiftClosingDialog(self.shift_id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.shift_ended = True
            self.accept()
        else:
            self.refresh()
