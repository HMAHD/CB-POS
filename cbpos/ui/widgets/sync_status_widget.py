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
import weakref

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolTip,
    QWidget,
)

from cbpos.i18n import _t, register_language_callback, unregister_language_callback

logger = logging.getLogger(__name__)


class SyncStatusWidget(QWidget):
    """Compact sync status indicator for the main window."""

    # Style constants
    COLORS = {
        "connected": "#4CAF50",  # Green
        "syncing": "#FFC107",  # Amber
        "disconnected": "#F44336",  # Red
        "main": "#9C27B0",  # Purple
        "standalone": "#607D8B",  # Blue-grey
        "error": "#FF5722",  # Deep orange
    }

    def __init__(self, parent=None):
        """Create the hidden status indicator (dot + label).

        Made visible once a sync mode is set via ``set_mode()``.
        """
        super().__init__(parent)
        self._mode: str = "standalone"  # standalone, main, terminal
        self._state: str = "disconnected"
        self._pending: int = 0
        self._connected_terminals: int = 0
        self._server_address: str = ""
        self._last_sync: str = ""
        self._config_error: str = ""

        self._setup_ui()
        register_language_callback(self.retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        def _unregister():
            widget = self_ref()
            if widget is not None:
                unregister_language_callback(widget.retranslate_ui)

        self.destroyed.connect(_unregister)

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
        self._dot.setStyleSheet(f"color: {self.COLORS['standalone']}; font-size: 12px;")
        layout.addWidget(self._dot)

        # Status label
        self._label = QLabel("")
        self._label.setStyleSheet("font-size: 11px; color: #aaa; padding: 0 4px;")
        layout.addWidget(self._label)

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(_t("sync_status.tooltip"))

        # Start hidden — only show when mode is main or terminal
        self.setVisible(False)

    def mousePressEvent(self, event):
        """Show sync details on click."""
        details = self._build_details_text()
        QToolTip.showText(self.mapToGlobal(event.pos()), details, self)

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
        elif self._mode == "terminal":
            state_labels = {
                "connected": _t("sync_status.status_connected"),
                "syncing": _t("sync_status.status_syncing"),
                "error": _t("sync_status.status_error"),
                "disconnected": _t("sync_status.status_disconnected"),
            }
            lines.append(f"<b>{mode_label}:</b> {_t('sync_status.detail_mode_terminal')}")
            lines.append(f"<b>{_t('sync_status.detail_main_pc')}:</b> {self._server_address}")
            lines.append(f"<b>{_t('common.status')}:</b> {state_labels.get(self._state, self._state)}")
            lines.append(
                f"<b>{_t('sync_status.detail_pending')}:</b> "
                f"{_t('sync_status.detail_pending_records', count=self._pending)}"
            )
            if self._last_sync:
                lines.append(f"<b>{_t('sync_status.detail_last_sync')}:</b> {self._last_sync}")
        else:
            lines.append(f"<b>{mode_label}:</b> {_t('sync_status.detail_mode_standalone')}")

        return "<br>".join(lines)

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
    def set_state(self, state: str) -> None:
        """Update the connection state (for terminal mode)."""
        self._state = state
        self._update_display()

    @pyqtSlot(str)
    def set_server_address(self, address: str) -> None:
        """Set the server address display (for main or terminal mode)."""
        self._server_address = address
        self._update_display()

    @pyqtSlot(str)
    def on_terminal_connected(self, terminal_id: str) -> None:
        """Update when a terminal connects (for main mode)."""
        self._connected_terminals += 1
        self._update_display()

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
            color = self.COLORS["error"]
            text = _t("sync_status.disabled")
        elif self._mode == "main":
            color = self.COLORS["main"]
            text = _t("sync_status.main_label", count=self._connected_terminals)
        elif self._mode == "terminal":
            color = self.COLORS.get(self._state, self.COLORS["disconnected"])
            if self._state == "connected":
                if self._pending > 0:
                    text = _t("sync_status.synced_pending", pending=self._pending)
                else:
                    text = _t("sync_status.synced")
            elif self._state == "syncing":
                text = _t("sync_status.syncing", pending=self._pending)
            elif self._state == "error":
                text = _t("sync_status.error_label")
            else:
                text = _t("sync_status.disconnected")
        else:
            color = self.COLORS["standalone"]
            text = ""

        self._dot.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._label.setText(text)
