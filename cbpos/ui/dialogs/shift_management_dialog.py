"""One place for everything about the cashier's open shift (#605)."""

import logging
from datetime import datetime
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
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.printer_service import PrinterService
from cbpos.core.services.shift_service import ShiftService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency, format_datetime, format_relative_time
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.cash_movement_dialog import CashMovementDialog
from cbpos.ui.dialogs.force_close_shift_dialog import ForceCloseShiftDialog
from cbpos.ui.dialogs.shift_closing_dialog import ShiftClosingDialog
from cbpos.ui.dialogs.stale_shifts_dialog import StaleShiftsDialog
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
        self._print_job_id: str | None = None
        PrintWorker.instance().job_result.connect(self._on_x_read_job_result)

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

        # Stale shift warning banner (#884)
        self.stale_banner = QFrame()
        self.stale_banner.setObjectName("ShiftStaleBanner")
        self.stale_banner.setProperty("class", "warning-banner")
        stale_layout = QVBoxLayout(self.stale_banner)
        stale_layout.setContentsMargins(12, 10, 12, 10)
        stale_layout.setSpacing(8)

        stale_hdr = QHBoxLayout()
        self.lbl_stale_icon = QLabel()
        self.lbl_stale_icon.setPixmap(Icons.get("fa5s.exclamation-triangle", "#FFDC00").pixmap(16, 16))
        stale_hdr.addWidget(self.lbl_stale_icon)

        self.lbl_stale_badge = QLabel()
        self.lbl_stale_badge.setObjectName("ShiftStaleLabel")
        stale_hdr.addWidget(self.lbl_stale_badge, 1)
        stale_layout.addLayout(stale_hdr)

        stale_btns = QHBoxLayout()
        stale_btns.setSpacing(8)
        self.btn_force_close = QPushButton()
        self.btn_force_close.setObjectName("ShiftForceCloseBtn")
        self.btn_force_close.setProperty("class", "danger")
        self.btn_force_close.clicked.connect(self._on_force_close)
        stale_btns.addWidget(self.btn_force_close)

        self.btn_view_other_stale = QPushButton()
        self.btn_view_other_stale.setObjectName("ShiftViewOtherStaleBtn")
        self.btn_view_other_stale.setProperty("class", "secondary")
        self.btn_view_other_stale.clicked.connect(self._on_view_other_stale)
        stale_btns.addWidget(self.btn_view_other_stale)
        stale_btns.addStretch()

        stale_layout.addLayout(stale_btns)
        self.stale_banner.setVisible(False)
        layout.addWidget(self.stale_banner)

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
        self.btn_force_close.setText(_t("shift_management.btn_force_close"))

    def refresh(self) -> None:
        """Reload the X-read figures from ``ShiftService``."""
        service = ShiftService()
        summary = service.get_shift_summary(self.shift_id)
        self._summary = summary
        for key, _ in _MONEY_ROWS:
            self.value_labels[key].setText(format_currency(summary.get(key) or Decimal(0)))
        for key, _ in _COUNT_ROWS:
            self.value_labels[key].setText(str(summary.get(key) or 0))
        start = summary.get("start_time")
        if start:
            rel_time = format_relative_time(start)
            exact_time = format_datetime(start)
            self.lbl_started.setText(_t("shift_management.started", time=rel_time, user=summary.get("user_name", "")))
            self.lbl_started.setToolTip(exact_time)
        else:
            self.lbl_started.setText("")
            self.lbl_started.setToolTip("")

        # Check staleness (#884)
        current_term = ConfigService.get("terminal_id") or "TERM-01"
        shift_term = summary.get("terminal_id")
        reasons = []

        if start and (datetime.now() - start).total_seconds() > 24 * 3600:
            reasons.append(_t("shift_management.stale_time_warning"))
        if shift_term and shift_term != current_term:
            reasons.append(_t("shift_management.stale_terminal_warning", terminal=shift_term))

        current_user = AuthService.get_current_user()
        can_force = bool(
            current_user and PermissionService.user_has_permission(current_user, Permissions.SHIFT_FORCE_CLOSE)
        )

        if reasons:
            self.stale_banner.setVisible(True)
            self.lbl_stale_badge.setText(_t("shift_management.stale_tag") + " — " + " · ".join(reasons))
            self.btn_force_close.setVisible(can_force)
        else:
            self.stale_banner.setVisible(False)

        # Other stale shifts
        other_stale = [s for s in service.get_stale_shifts(current_term) if s.id != self.shift_id]
        if other_stale and can_force:
            self.btn_view_other_stale.setVisible(True)
            self.btn_view_other_stale.setText(_t("shift_management.btn_view_stale", count=len(other_stale)))
        else:
            self.btn_view_other_stale.setVisible(False)

    def _on_force_close(self) -> None:
        dialog = ForceCloseShiftDialog(self.shift_id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.shift_ended = True
            self.accept()

    def _on_view_other_stale(self) -> None:
        dialog = StaleShiftsDialog(parent=self)
        dialog.exec()
        self.refresh()

    def _print_x_read(self) -> None:
        """Print the current figures as an X-Read; report the printer's real outcome."""
        self.btn_print_x_read.setEnabled(False)
        try:
            self._print_job_id = PrinterService.print_shift_report(self._summary, x_read=True)
        except Exception as e:
            logger.error("X-Read could not be built: %s", e)
            self._on_x_read_error(str(e))

    def _disconnect_print_signals(self, worker: PrintWorker) -> None:
        pass

    def _on_x_read_job_result(self, job_id: str, ok: bool, message: str) -> None:
        """Called once the queued print job actually finishes."""
        if self._print_job_id is None or job_id != self._print_job_id:
            return
        self._print_job_id = None
        if ok:
            self._on_x_read_printed()
        else:
            self._on_x_read_error(message)

    def _on_x_read_printed(self) -> None:
        self.btn_print_x_read.setEnabled(True)
        QMessageBox.information(self, _t("common.success"), _t("shift_management.x_read_printed"))

    def _on_x_read_error(self, message: str) -> None:
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
            QMessageBox.critical(
                self, _t("common.error"), _t("shift_management.movement_failed", error=translate_error(str(e)))
            )
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
