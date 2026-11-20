"""Dialog offering to recover or discard an unfinished bill saved during a power cut (#932)."""

import logging
from enum import IntEnum

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.core.utils.formatters import format_currency, format_datetime
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class AutosaveAction(IntEnum):
    """User choice when handling an interrupted bill at startup."""

    IGNORE = 0
    CONTINUE = 1
    DISCARD = 2


class AutosaveRecoveryDialog(QDialog):
    """Prompts cashier to restore or discard an interrupted bill found at startup/login."""

    def __init__(self, summary: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AutosaveRecoveryDialog")
        self.summary = summary
        self.terminal_id = summary.get("terminal_id", "")
        self.action = AutosaveAction.IGNORE

        self.setWindowTitle(_t("autosave.recovery_title"))
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Card container
        card = QFrame(self)
        card.setObjectName("AutosaveRecoveryCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        header_lbl = QLabel(_t("autosave.recovery_header"), card)
        header_lbl.setObjectName("AutosaveHeader")
        header_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        card_layout.addWidget(header_lbl)

        count = self.summary.get("item_count", 0)
        total = self.summary.get("total", 0)
        total_str = format_currency(total)

        body_lbl = QLabel(
            _t(
                "autosave.recovery_body",
                count=count,
                total=total_str,
                default=f"You had an unfinished bill with {count} items ({total_str}). Would you like to restore it?",
            ),
            card,
        )
        body_lbl.setObjectName("AutosaveBody")
        body_lbl.setWordWrap(True)
        card_layout.addWidget(body_lbl)

        timestamp = self.summary.get("timestamp")
        if timestamp:
            time_str = format_datetime(timestamp)
            time_lbl = QLabel(_t("autosave.saved_at", time=time_str, default=f"Saved at: {time_str}"), card)
            time_lbl.setObjectName("AutosaveTimestamp")
            time_lbl.setStyleSheet("color: #888888; font-size: 12px;")
            card_layout.addWidget(time_lbl)

        layout.addWidget(card)

        # Footer with Continue (Primary) and Discard (Secondary/Danger)
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        self.btn_discard = QPushButton(_t("autosave.btn_discard"), self)
        self.btn_discard.setObjectName("BtnDiscardAutosave")
        self.btn_discard.setProperty("class", "danger")
        self.btn_discard.setMinimumHeight(38)
        self.btn_discard.clicked.connect(self._on_discard)
        footer_layout.addWidget(self.btn_discard)

        footer_layout.addStretch()

        self.btn_continue = QPushButton(_t("autosave.btn_continue"), self)
        self.btn_continue.setObjectName("BtnContinueAutosave")
        self.btn_continue.setProperty("class", "primary")
        self.btn_continue.setMinimumHeight(38)
        self.btn_continue.setDefault(True)
        self.btn_continue.setAutoDefault(True)
        self.btn_continue.clicked.connect(self._on_continue)
        footer_layout.addWidget(self.btn_continue)

        layout.addLayout(footer_layout)

    def _on_continue(self) -> None:
        self.action = AutosaveAction.CONTINUE
        self.accept()

    def _on_discard(self) -> None:
        ans = QMessageBox.question(
            self,
            _t("autosave.discard_confirm_title", default="Discard Unfinished Bill?"),
            _t(
                "autosave.discard_confirm_body",
                default="Are you sure you want to discard this bill? The unsaved cart will be permanently deleted.",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            ok = CartAutosaveService.discard_autosave(self.terminal_id)
            if not ok:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("errors.discard_failed", default="Failed to discard autosaved bill. Please try again."),
                )
                return
            self.action = AutosaveAction.DISCARD
            self.accept()

    def keyPressEvent(self, event) -> None:
        """Handle escape key to leave the prompt without discarding."""
        if event.key() == Qt.Key.Key_Escape:
            self.action = AutosaveAction.IGNORE
            self.reject()
        else:
            super().keyPressEvent(event)
