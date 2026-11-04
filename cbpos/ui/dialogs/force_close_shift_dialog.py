"""Dialog for force-closing an orphaned or stale shift (#884).

Requires shift.force_close permission. Asks for counted cash (or "Don't know")
and a required reason, writing SHIFT_FORCE_CLOSED to AuditLog.
"""

import logging
from decimal import Decimal, InvalidOperation

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.shift_service import ShiftService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class ForceCloseShiftDialog(QDialog):
    """Force close a shift with counted cash (or unknown) and a required reason."""

    def __init__(self, shift_id: int, parent=None):
        super().__init__(parent)
        self.shift_id = shift_id
        self.setObjectName("ForceCloseShiftDialog")
        self.setMinimumWidth(440)
        self._init_ui()
        self.retranslate_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        layout.addWidget(self.lbl_title)

        self.lbl_prompt = QLabel()
        self.lbl_prompt.setProperty("class", "muted")
        layout.addWidget(self.lbl_prompt)

        # Counted cash field
        self.lbl_cash = QLabel()
        layout.addWidget(self.lbl_cash)

        self.txt_cash = QLineEdit()
        self.txt_cash.setObjectName("ForceCloseCashInput")
        self.txt_cash.setPlaceholderText("0.00")
        layout.addWidget(self.txt_cash)

        # "Don't know" checkbox
        self.chk_dont_know = QCheckBox()
        self.chk_dont_know.toggled.connect(self._on_dont_know_toggled)
        layout.addWidget(self.chk_dont_know)

        # Required reason
        self.lbl_reason = QLabel()
        layout.addWidget(self.lbl_reason)

        self.txt_reason = QLineEdit()
        self.txt_reason.setObjectName("ForceCloseReasonInput")
        self.txt_reason.textChanged.connect(self._on_reason_changed)
        layout.addWidget(self.txt_reason)

        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton()
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_confirm = QPushButton()
        self.btn_confirm.setObjectName("ForceCloseConfirmBtn")
        self.btn_confirm.setProperty("class", "danger")
        self.btn_confirm.setEnabled(False)  # Requires reason
        self.btn_confirm.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self.btn_confirm)

        layout.addLayout(btn_layout)

    def retranslate_ui(self) -> None:
        """Update user-facing text from current translations."""
        self.setWindowTitle(_t("shift_force_close.title"))
        self.lbl_title.setText(_t("shift_force_close.title"))
        self.lbl_cash.setText(_t("shift_force_close.counted_cash"))
        self.chk_dont_know.setText(_t("shift_force_close.dont_know"))
        self.lbl_reason.setText(_t("shift_force_close.reason"))
        self.txt_reason.setPlaceholderText(_t("shift_force_close.reason_placeholder"))
        self.btn_cancel.setText(_t("common.cancel"))
        self.btn_confirm.setText(_t("shift_force_close.submit"))

        # Fetch shift terminal to populate prompt
        try:
            summary = ShiftService().get_shift_summary(self.shift_id)
            term = summary.get("terminal_id") or "TERM-01"
            self.lbl_prompt.setText(_t("shift_force_close.prompt", id=self.shift_id, terminal=term))
        except Exception:
            self.lbl_prompt.setText(f"Shift #{self.shift_id}")

    def _on_dont_know_toggled(self, checked: bool) -> None:
        self.txt_cash.setEnabled(not checked)
        if checked:
            self.txt_cash.clear()

    def _on_reason_changed(self, text: str) -> None:
        self.btn_confirm.setEnabled(bool(text.strip()))

    def _on_confirm(self) -> None:
        reason = self.txt_reason.text().strip()
        if not reason:
            QMessageBox.warning(self, _t("common.warning"), _t("shift_force_close.reason_required"))
            return

        counted_cash = None
        if not self.chk_dont_know.isChecked():
            val_text = self.txt_cash.text().strip()
            if val_text:
                try:
                    counted_cash = Decimal(val_text)
                    if counted_cash < Decimal(0):
                        raise ValueError("Negative amount")
                except (InvalidOperation, ValueError):
                    QMessageBox.warning(self, _t("common.warning"), _t("shift_force_close.invalid_amount"))
                    return
            else:
                counted_cash = Decimal("0.00")

        current_user = AuthService.get_current_user()
        if not current_user:
            QMessageBox.critical(self, _t("common.error"), "No user logged in.")
            return

        try:
            ShiftService().force_close_shift(
                self.shift_id,
                counted_cash=counted_cash,
                reason=reason,
                closed_by_user_id=current_user.id,
            )
        except Exception as e:
            logger.error("Force close failed for shift %s: %s", self.shift_id, e)
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("shift_force_close.error", error=translate_error(str(e))),
            )
            return

        QMessageBox.information(self, _t("common.success"), _t("shift_force_close.success", id=self.shift_id))
        self.accept()
