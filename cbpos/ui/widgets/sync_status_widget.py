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

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QToolTip,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QCursor

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
        super().__init__(parent)
        self._mode: str = "standalone"  # standalone, main, terminal
        self._state: str = "disconnected"
        self._pending: int = 0
        self._connected_terminals: int = 0
        self._server_address: str = ""
        self._last_sync: str = ""
        self._config_error: str = ""

        self._setup_ui()

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
        self.setToolTip("Click for sync details")

        # Start hidden — only show when mode is main or terminal
        self.setVisible(False)

    def mousePressEvent(self, event):
        """Show sync details on click."""
        details = self._build_details_text()
        QToolTip.showText(self.mapToGlobal(event.pos()), details, self)

    def _build_details_text(self) -> str:
        lines = []
        if self._config_error:
            lines.append(f"<b>LAN Sync is not running:</b> {self._config_error}")
            lines.append("Fix this in Settings &rarr; Network &rarr; LAN Sync.")
            return "<br>".join(lines)
        if self._mode == "main":
            lines.append("<b>Mode:</b> Main PC (Sync Server)")
            lines.append(f"<b>Address:</b> {self._server_address}")
            lines.append(f"<b>Connected terminals:</b> {self._connected_terminals}")
        elif self._mode == "terminal":
            lines.append("<b>Mode:</b> Terminal")
            lines.append(f"<b>Main PC:</b> {self._server_address}")
            lines.append(f"<b>Status:</b> {self._state.title()}")
            lines.append(f"<b>Pending:</b> {self._pending} records")
            if self._last_sync:
                lines.append(f"<b>Last sync:</b> {self._last_sync}")
        else:
            lines.append("<b>Mode:</b> Standalone (no sync)")

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
            text = "Sync disabled — see Settings"
        elif self._mode == "main":
            color = self.COLORS["main"]
            text = f"Main PC · {self._connected_terminals} terminals"
        elif self._mode == "terminal":
            color = self.COLORS.get(self._state, self.COLORS["disconnected"])
            if self._state == "connected":
                if self._pending > 0:
                    text = f"Synced · {self._pending} pending"
                else:
                    text = "Synced"
            elif self._state == "syncing":
                text = f"Syncing · {self._pending} pending"
            elif self._state == "error":
                text = "Sync Error"
            else:
                text = "Disconnected"
        else:
            color = self.COLORS["standalone"]
            text = ""

        self._dot.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._label.setText(text)
