"""
Sync Status Widget for CB-POS Multi-Terminal LAN Sync.

A small, unobtrusive status indicator that sits in the main window's
top-right corner.  Shows the current sync state with a colored dot
and brief label.

Design:
- 🟢 "Synced" — connected and all transactions pushed
- 🟡 "Syncing (3 pending)" — actively syncing
- 🔴 "Disconnected" — cannot reach Main PC
- 🟣 "Main PC" — this machine is the sync server
"""

import logging

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.i18n import _t, register_language_callback
from cbpos.ui.utils.style_helpers import refresh_style
from cbpos.ui.widgets.dialog_footer import make_dialog_footer

logger = logging.getLogger(__name__)


class SyncDetailsDialog(QDialog):
    """Detailed sync status dialog showing connection info, pending records,
    and recent sync errors with an immediate Retry action."""

    def __init__(self, status_widget: "SyncStatusWidget", parent=None):
        super().__init__(parent or status_widget)
        self.setWindowTitle(_t("sync.dialog_title"))
        self.setObjectName("SyncDetailsDialog")
        self.setMinimumWidth(440)
        self._status_widget = status_widget
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Status text summary
        details_label = QLabel(self._status_widget._build_details_text())
        details_label.setTextFormat(Qt.TextFormat.RichText)
        details_label.setWordWrap(True)
        layout.addWidget(details_label)

        # Recent errors section if present
        if self._status_widget._recent_errors:
            err_title = QLabel(f"<b>{_t('sync.recent_errors')}:</b>")
            layout.addWidget(err_title)

            error_list = QListWidget()
            error_list.setMaximumHeight(160)
            for err in self._status_widget._recent_errors:
                item = QListWidgetItem(str(err))
                error_list.addItem(item)
            layout.addWidget(error_list)

        # Footer
        if self._status_widget._mode == "terminal":
            footer_layout, _, _ = make_dialog_footer(
                primary_key="sync.retry_now",
                on_primary=self._on_retry,
                cancel_key="common.close",
                on_cancel=self.reject,
                primary_object_name="BtnRetrySync",
                cancel_object_name="BtnClose",
            )
        else:
            footer_layout, _, btn_close = make_dialog_footer(
                primary_key="common.close",
                on_primary=self.accept,
                cancel_key="common.close",
                on_cancel=self.reject,
            )
            btn_close.setVisible(False)
        layout.addLayout(footer_layout)

    def _on_retry(self):
        self._status_widget.retry_requested.emit()
        self.accept()


class SyncStatusWidget(QWidget):
    """Compact sync status indicator for the main window."""

    retry_requested = pyqtSignal()

    # Style constants
    COLORS = {
        "connected": "#4CAF50",  # Green
        "syncing": "#FFC107",  # Amber
        "disconnected": "#F44336",  # Red
        "main": "#9C27B0",  # Purple
        "standalone": "#607D8B",  # Blue-grey
        "error": "#FF5722",  # Deep orange
        "unpaired": "#FFC107",  # Amber
    }

    def __init__(self, parent=None):
        """Create the hidden status indicator (dot + label).

        Made visible once a sync mode is set via ``set_mode()``.
        """
        super().__init__(parent)
        self._mode: str = "standalone"  # standalone, main, terminal
        self._state: str = "disconnected"
        self._error_code: str | None = None
        self._server_error: str | None = None
        self._recent_errors: list[str] = []
        self._pending: int = 0
        self._connected_terminals: int = 0
        self._server_address: str = ""
        self._last_sync: str = ""
        self._config_error: str = ""

        self._setup_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def retranslate_ui(self) -> None:
        """Update the tooltip and status text from i18n (called on language change)."""
        self.setToolTip(_t("sync_status.tooltip"))
        self._update_display()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        # Status dot (●)
        self._dot = QLabel("●")
        self._dot.setObjectName("SyncDot")
        self._dot.setProperty("status", "standalone")
        layout.addWidget(self._dot)

        # Status label
        self._label = QLabel("")
        self._label.setObjectName("SyncLabel")
        layout.addWidget(self._label)

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(_t("sync_status.tooltip"))

        # Start hidden — only show when mode is main or terminal
        self.setVisible(False)

    def mousePressEvent(self, event):
        """Show sync details dialog on click."""
        dialog = SyncDetailsDialog(self, self.window())
        dialog.exec()

    def _build_details_text(self) -> str:
        lines = []
        if self._config_error:
            lines.append(f"<b>{_t('sync_status.detail_error_prefix')}</b> {self._config_error}")
            lines.append(_t("sync_status.detail_fix_hint"))
            return "<br>".join(lines)
        mode_label = _t("sync_status.detail_mode_label")
        if self._mode == "main":
            lines.append(f"<b>{mode_label}:</b> {_t('sync_status.detail_mode_main')}")
            lines.append(f"<b>{_t('sync_status.detail_address')}:</b> {self._server_address}")
            lines.append(f"<b>{_t('sync_status.detail_connected_terminals')}:</b> {self._connected_terminals}")
            if self._server_error:
                lines.append(f"<span style='color: #F44336;'><b>{_t('common.error')}:</b> {self._server_error}</span>")
        elif self._mode == "terminal":
            state_labels = {
                "connected": _t("sync_status.status_connected"),
                "syncing": _t("sync_status.status_syncing"),
                "error": _t("sync_status.status_error"),
                "disconnected": _t("sync_status.status_disconnected"),
                "unpaired": _t("sync_pairing.not_paired_short"),
            }
            lines.append(f"<b>{mode_label}:</b> {_t('sync_status.detail_mode_terminal')}")
            lines.append(f"<b>{_t('sync_status.detail_main_pc')}:</b> {self._server_address}")
            lines.append(f"<b>{_t('common.status')}:</b> {state_labels.get(self._state, _t('common.unknown'))}")
            if self._state == "unpaired":
                lines.append(f"<span style='color: #FFC107;'>{_t('sync_pairing.not_paired')}</span>")
            elif self._state == "error" and self._error_code == "cert_mismatch":
                lines.append(f"<span style='color: #F44336;'>{_t('sync_pairing.changed')}</span>")
            elif self._state == "error" and self._error_code == "terminal_id_is_main":
                lines.append(f"<span style='color: #F44336;'>{_t('sync.error_terminal_id_is_main')}</span>")
            elif self._state == "error" and self._error_code == "terminal_id_taken":
                from cbpos.core.services.config_service import ConfigService

                tid = ConfigService.get("terminal_id") or ""
                lines.append(f"<span style='color: #F44336;'>{_t('sync.error_terminal_id_taken', id=tid)}</span>")
            elif self._state == "error" and self._error_code:
                lines.append(f"<span style='color: #F44336;'>{self._format_reason(self._error_code)}</span>")
            else:
                lines.append(
                    f"<b>{_t('sync_status.detail_pending')}:</b> "
                    f"{_t('sync_status.detail_pending_records', count=self._pending)}"
                )
                if self._last_sync:
                    lines.append(f"<b>{_t('sync_status.detail_last_sync')}:</b> {self._last_sync}")
        else:
            lines.append(f"<b>{mode_label}:</b> {_t('sync_status.detail_mode_standalone')}")

        return "<br>".join(lines)

    def _format_reason(self, code: str) -> str:
        """Format an error code into a human-readable translated message."""
        if not code:
            return _t("sync.reason_connection_failed")
        code_key = f"sync.reason_{code}"
        translated = _t(code_key)
        if translated != code_key:
            return translated
        lower = code.lower()
        if "bind" in lower or "address already in use" in lower or "port" in lower:
            return _t("sync.reason_bind_failed")
        if "500" in code or "rejected" in lower:
            return _t("sync.reason_server_error")
        if "connection" in lower or "refused" in lower or "timed out" in lower:
            return _t("sync.reason_connection_failed")
        return code

    # --- Public API ---

    def set_mode(self, mode: str) -> None:
        """Set the terminal mode: 'standalone', 'main', or 'terminal'."""
        self._mode = mode
        self.setVisible(mode in ("main", "terminal"))
        self._update_display()

    def set_config_error(self, message: str) -> None:
        """Show a persistent configuration error (e.g. missing Shared Secret).

        Distinct from the transient connection ``error`` state: this means
        sync was never started at all, not that it dropped mid-session.
        Call with an empty string to clear it. The widget is made visible
        even in modes that would otherwise stay hidden, since the whole
        point is to tell the user *why* the sync they configured isn't
        running.
        """
        self._config_error = message
        if message:
            self.setVisible(True)
        self._update_display()

    @pyqtSlot(str)
    def set_state(self, state: str, error_code: str | None = None) -> None:
        """Update the connection state (for terminal mode)."""
        self._state = state
        if error_code is not None:
            self._error_code = error_code
        elif state != "error":
            self._error_code = None
        self._update_display()

    @pyqtSlot(str)
    def set_error_code(self, code: str | None) -> None:
        """Set the error code (e.g. 'cert_mismatch')."""
        self._error_code = code
        self._update_display()

    @pyqtSlot(str)
    def on_sync_error(self, message: str) -> None:
        """Handle error signal from sync client."""
        self._record_error(message)
        self._state = "error"
        if message in (_t("sync_pairing.changed"), "cert_mismatch"):
            self._error_code = "cert_mismatch"
        elif message in ("terminal_id_is_main", "terminal_id_taken", "protocol_too_old"):
            self._error_code = message
        elif "500" in message or "rejected" in message.lower():
            self._error_code = "server_error"
        elif "connection" in message.lower() or "refused" in message.lower() or "timed out" in message.lower():
            self._error_code = "connection_failed"
        else:
            self._error_code = message
        self._update_display()

    @pyqtSlot(str)
    def on_server_error(self, message: str) -> None:
        """Handle error signal from sync server (Main PC mode)."""
        self._server_error = message
        self._state = "error"
        if "bind" in message.lower() or "address" in message.lower() or "port" in message.lower():
            self._error_code = "bind_failed"
        else:
            self._error_code = "server_error"
        self._record_error(message)
        self._update_display()

    @pyqtSlot(list)
    def set_recent_errors(self, errors: list[str]) -> None:
        """Update recent sync errors list."""
        self._recent_errors = errors[:10]

    def _record_error(self, error: str) -> None:
        if error and error not in self._recent_errors:
            self._recent_errors.insert(0, error)
            self._recent_errors = self._recent_errors[:10]

    @pyqtSlot(str)
    def set_server_address(self, address: str) -> None:
        """Set the server address display (for main or terminal mode)."""
        self._server_address = address
        self._update_display()

    @pyqtSlot(str)
    def on_terminal_connected(self, terminal_id: str) -> None:
        """Update when a terminal connects (for main mode). Counts distinct active terminals."""
        self._refresh_connected_terminals()

    def _refresh_connected_terminals(self) -> int:
        """Count distinct terminals seen in the last 5 minutes that are not released (#906)."""
        from cbpos.core.services.sync_terminal_service import SyncTerminalService

        self._connected_terminals = SyncTerminalService.count_active_terminals(window_minutes=5)
        self._update_display()
        return self._connected_terminals

    @pyqtSlot(str, int)
    def on_sync_completed(self, terminal_id: str, count: int) -> None:
        """Update after a sync cycle completes (for main mode)."""
        from datetime import datetime

        self._last_sync = datetime.now().strftime("%H:%M:%S")
        self._update_display()

    @pyqtSlot(int, int)
    def on_client_sync_completed(self, pushed: int, pulled: int) -> None:
        """Update after a sync cycle (for terminal mode)."""
        from datetime import datetime

        self._last_sync = datetime.now().strftime("%H:%M:%S")
        self._pending = max(0, self._pending - pushed)
        self._update_display()

    def set_pending_count(self, count: int) -> None:
        """Update the pending (unsynced) record count."""
        self._pending = count
        self._update_display()

    def set_terminal_count(self, count: int) -> None:
        """Update the connected terminal count (main mode)."""
        self._connected_terminals = count
        self._update_display()

    def _update_display(self) -> None:
        """Refresh the dot color and label text based on current state."""
        if self._config_error:
            status = "error"
            text = _t("sync_status.disabled")
        elif self._mode == "main":
            if self._server_error:
                status = "error"
                reason = self._format_reason(self._error_code or "bind_failed")
                text = _t("sync.main_error", reason=reason)
            else:
                status = "main"
                text = _t("sync.main_tills", count=self._connected_terminals)
        elif self._mode == "terminal":
            if self._state == "unpaired":
                status = "unpaired"
                text = _t("sync_pairing.not_paired_short")
            elif self._state in ("error", "disconnected"):
                status = "error" if self._state == "error" else "disconnected"
                if self._error_code == "cert_mismatch":
                    text = _t("sync_pairing.changed")
                else:
                    reason = self._format_reason(self._error_code or "connection_failed")
                    text = _t("sync.not_sending", reason=reason)
            elif self._state == "syncing":
                status = "syncing"
                text = _t("sync.sending", count=self._pending)
            elif self._state == "connected":
                status = "connected"
                if self._pending > 0:
                    text = _t("sync_status.synced_pending", pending=self._pending)
                else:
                    text = _t("sync.status_synced")
            else:
                status = "disconnected"
                text = _t("sync_status.disconnected")
        else:
            status = "standalone"
            text = ""

        self._dot.setProperty("status", status)
        refresh_style(self._dot)
        self._label.setText(text)
