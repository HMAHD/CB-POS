"""Dialog displaying full log entry details and multi-line tracebacks."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.i18n import _t
from cbpos.ui.utils.style_helpers import set_status_class


class LogDetailDialog(QDialog):
    """Modal dialog displaying formatted metadata and full stack trace for a log entry."""

    def __init__(self, entry: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(_t("admin_tools.logs_detail_dialog_title"))
        self.setMinimumSize(680, 480)
        self.resize(760, 520)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header title
        title_lbl = QLabel(_t("admin_tools.logs_detail_dialog_title"))
        title_lbl.setProperty("class", "dialog-title")
        layout.addWidget(title_lbl)

        # Metadata info row
        info_layout = QHBoxLayout()
        info_layout.setSpacing(16)

        time_text = self.entry.get("timestamp", "--")
        lbl_time = QLabel(f"<b>{_t('admin_tools.logs_header_time')}:</b> {time_text}")
        lbl_time.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(lbl_time)

        level_text = self.entry.get("level", "--")
        lbl_level_prefix = QLabel(f"<b>{_t('admin_tools.logs_header_level')}:</b>")
        info_layout.addWidget(lbl_level_prefix)

        self.lbl_level = QLabel(level_text)
        if level_text in ("CRITICAL", "ERROR"):
            set_status_class(self.lbl_level, "debit")
        elif level_text == "WARNING":
            set_status_class(self.lbl_level, "warning-hint")
        else:
            set_status_class(self.lbl_level, "bold")
        info_layout.addWidget(self.lbl_level)

        source_text = self.entry.get("source", "--")
        lbl_source = QLabel(f"<b>{_t('admin_tools.logs_header_source')}:</b> {source_text}")
        lbl_source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(lbl_source)

        info_layout.addStretch()
        layout.addLayout(info_layout)

        # Message & Traceback label
        lbl_msg_title = QLabel(_t("admin_tools.logs_header_message"))
        lbl_msg_title.setProperty("class", "bold")
        layout.addWidget(lbl_msg_title)

        # Multi-line monospace text area
        self.txt_message = QPlainTextEdit()
        self.txt_message.setReadOnly(True)
        self.txt_message.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        self.txt_message.setFont(font)
        self.txt_message.setPlainText(self.entry.get("message", ""))
        layout.addWidget(self.txt_message, 1)

        # Action Buttons footer
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_copy = QPushButton(_t("admin_tools.logs_btn_copy_details"))
        self.btn_copy.clicked.connect(self._copy_details)
        btn_layout.addWidget(self.btn_copy)

        btn_layout.addStretch()

        self.btn_close = QPushButton(_t("common.close"))
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # Keyboard shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.reject)

    def _copy_details(self) -> None:
        """Copy formatted log details (timestamp, level, source, message) to clipboard."""
        details = (
            f"Timestamp: {self.entry.get('timestamp', '')}\n"
            f"Level:     {self.entry.get('level', '')}\n"
            f"Source:    {self.entry.get('source', '')}\n"
            f"Message:\n{self.entry.get('message', '')}"
        )
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(details)
