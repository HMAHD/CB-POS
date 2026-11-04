"""Dialog listing stale open shifts with actions to force-close them (#884)."""

import logging
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.shift_service import ShiftService
from cbpos.core.utils.formatters import format_currency, format_datetime
from cbpos.i18n import _t
from cbpos.ui.dialogs.force_close_shift_dialog import ForceCloseShiftDialog

logger = logging.getLogger(__name__)


class StaleShiftsDialog(QDialog):
    """View and force-close stale open shifts across terminals."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StaleShiftsDialog")
        self.setMinimumSize(640, 360)
        self._init_ui()
        self.retranslate_ui()
        self.load_shifts()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        layout.addWidget(self.lbl_title)

        self.lbl_heading = QLabel()
        self.lbl_heading.setProperty("class", "muted")
        layout.addWidget(self.lbl_heading)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.lbl_empty = QLabel()
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setProperty("class", "muted")
        self.lbl_empty.setVisible(False)
        layout.addWidget(self.lbl_empty)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton()
        self.btn_close.setProperty("class", "secondary")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def retranslate_ui(self) -> None:
        """Update user-facing text from current translations."""
        self.setWindowTitle(_t("stale_shifts.title"))
        self.lbl_title.setText(_t("stale_shifts.title"))
        self.lbl_heading.setText(_t("stale_shifts.heading"))
        self.lbl_empty.setText(_t("stale_shifts.empty"))
        self.btn_close.setText(_t("common.close"))

        headers = [
            _t("stale_shifts.col_id"),
            _t("stale_shifts.col_terminal"),
            _t("stale_shifts.col_cashier"),
            _t("stale_shifts.col_started"),
            _t("stale_shifts.col_expected"),
            "",
        ]
        self.table.setHorizontalHeaderLabels(headers)

    def load_shifts(self) -> None:
        """Populate the table with stale open shifts across terminals."""
        service = ShiftService()
        stale_shifts = service.get_stale_shifts()

        if not stale_shifts:
            self.table.setVisible(False)
            self.lbl_empty.setVisible(True)
            return

        self.table.setVisible(True)
        self.lbl_empty.setVisible(False)
        self.table.setRowCount(len(stale_shifts))

        for row, shift in enumerate(stale_shifts):
            summary = service.get_shift_summary(shift.id)
            expected = summary.get("expected_cash") or Decimal("0")
            cashier_name = summary.get("user_name") or str(shift.user_id)
            started_str = format_datetime(shift.start_time) if shift.start_time else ""

            self.table.setItem(row, 0, QTableWidgetItem(f"#{shift.id}"))
            self.table.setItem(row, 1, QTableWidgetItem(shift.terminal_id or ""))
            self.table.setItem(row, 2, QTableWidgetItem(cashier_name))
            self.table.setItem(row, 3, QTableWidgetItem(started_str))
            self.table.setItem(row, 4, QTableWidgetItem(format_currency(expected)))

            btn_action = QPushButton(_t("stale_shifts.action_force_close"))
            btn_action.setProperty("class", "danger")
            btn_action.clicked.connect(lambda _, s_id=shift.id: self._force_close_shift(s_id))
            self.table.setCellWidget(row, 5, btn_action)

    def _force_close_shift(self, shift_id: int) -> None:
        dialog = ForceCloseShiftDialog(shift_id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_shifts()
