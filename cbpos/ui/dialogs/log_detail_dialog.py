"""Dialog displaying full log entry details and multi-line tracebacks."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.utils.formatters import format_relative_time
from cbpos.i18n import _t
from cbpos.ui.utils.style_helpers import refresh_style


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

        # Metadata Card (structured, not inline)
        meta_card = QFrame()
        meta_card.setObjectName("LogMetaCard")
        meta_layout = QFormLayout(meta_card)
        meta_layout.setContentsMargins(14, 10, 14, 10)
        meta_layout.setVerticalSpacing(8)
        meta_layout.setHorizontalSpacing(16)
        meta_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        meta_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Row 1: Level badge
        lbl_level_key = QLabel(_t("admin_tools.logs_header_level"))
        lbl_level_key.setProperty("class", "bold")

        level_text = (self.entry.get("level") or "INFO").strip()
        self.lbl_level = QLabel(level_text)
        self.lbl_level.setObjectName("LogLevelBadge")
        self.lbl_level.setProperty("level", level_text.upper())
        refresh_style(self.lbl_level)

        level_row = QHBoxLayout()
        level_row.setContentsMargins(0, 0, 0, 0)
        level_row.addWidget(self.lbl_level)
        level_row.addStretch()
        meta_layout.addRow(lbl_level_key, level_row)

        # Row 2: Time (Relative time as primary, exact timestamp as secondary)
        lbl_time_key = QLabel(_t("admin_tools.logs_header_time"))
        lbl_time_key.setProperty("class", "bold")

        raw_timestamp = self.entry.get("timestamp", "").strip()
        relative_str = format_relative_time(raw_timestamp) or raw_timestamp

        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(8)

        self.lbl_relative_time = QLabel(relative_str)
        self.lbl_relative_time.setProperty("class", "bold")
        self.lbl_relative_time.setToolTip(raw_timestamp)
        time_row.addWidget(self.lbl_relative_time)

        if raw_timestamp:
            clean_display_time = raw_timestamp.split(",")[0].split(".")[0]
            self.lbl_exact_time = QLabel(f"({clean_display_time})")
            self.lbl_exact_time.setProperty("class", "muted")
            self.lbl_exact_time.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.lbl_exact_time.setToolTip(raw_timestamp)
            time_row.addWidget(self.lbl_exact_time)

        time_row.addStretch()
        meta_layout.addRow(lbl_time_key, time_row)

        # Row 3: Source component
        lbl_source_key = QLabel(_t("admin_tools.logs_header_source"))
        lbl_source_key.setProperty("class", "bold")

        source_text = self.entry.get("source", "--").strip()
        self.lbl_source = QLabel(source_text)
        self.lbl_source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_source.setToolTip(source_text)
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(11)
        self.lbl_source.setFont(mono_font)
        meta_layout.addRow(lbl_source_key, self.lbl_source)

        layout.addWidget(meta_card)

        # Message & Traceback section
        lbl_msg_title = QLabel(_t("admin_tools.logs_header_message"))
        lbl_msg_title.setProperty("class", "bold")
        layout.addWidget(lbl_msg_title)

        # Multi-line monospace text area
        self.txt_message = QPlainTextEdit()
        self.txt_message.setReadOnly(True)
        self.txt_message.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.txt_message.setFont(mono_font)
        self.txt_message.setPlainText(self.entry.get("message", ""))
        layout.addWidget(self.txt_message, 1)

        # Action Buttons footer
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_copy = QPushButton(_t("admin_tools.logs_btn_copy_details"))
        self.btn_copy.setProperty("class", "secondary")
        self.btn_copy.clicked.connect(self._copy_details)
        btn_layout.addWidget(self.btn_copy)

        btn_layout.addStretch()

        self.btn_close = QPushButton(_t("common.close"))
        self.btn_close.setObjectName("BtnCancel")
        self.btn_close.setProperty("class", "secondary")
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # Keyboard shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.reject)

    def _copy_details(self) -> None:
        """Copy formatted log details (timestamp, relative time, level, source, message) to clipboard."""
        raw_timestamp = self.entry.get("timestamp", "").strip()
        relative_str = format_relative_time(raw_timestamp)
        details = (
            f"Timestamp: {raw_timestamp}\n"
            f"Time:      {relative_str}\n"
            f"Level:     {self.entry.get('level', '')}\n"
            f"Source:    {self.entry.get('source', '')}\n"
            f"Message:\n{self.entry.get('message', '')}"
        )
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(details)
