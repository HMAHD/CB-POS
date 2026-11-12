"""Reusable read-only viewer for bundled legal and license documents."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from cbpos.config import Config
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_close_footer

logger = logging.getLogger(__name__)


def get_bundled_document_path(filename: str) -> Path | None:
    """Resolve the filesystem path for a bundled document file.

    Checks sys._MEIPASS for PyInstaller frozen bundles, and Config.BASE_DIR
    for running from source.
    """
    candidates: list[Path] = []

    # Frozen PyInstaller bundle location
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / filename)

    # Source code repository root
    candidates.append(Config.BASE_DIR / filename)

    for path in candidates:
        if path.exists() and path.is_file():
            return path

    return None


class TextViewerDialog(QDialog):
    """Modal dialog displaying bundled legal notices or plain text documents."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TextViewerDialog")
        self.setWindowTitle(title)
        self.setMinimumSize(600, 480)
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setObjectName("DocumentText")
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(text)
        self.text_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.text_edit, 1)

        footer_layout, self.btn_close = make_close_footer(on_close=self.accept)
        layout.addLayout(footer_layout)

    @classmethod
    def show_document(cls, title: str, filename: str, parent: QWidget | None = None) -> bool:
        """Load a bundled document and display it in a TextViewerDialog.

        If the document cannot be found, displays a translated error notice.
        Returns True if displayed, False if missing.
        """
        path = get_bundled_document_path(filename)
        if path is None:
            logger.error("Bundled document %s could not be found", filename)
            QMessageBox.warning(
                parent,
                _t("common.error"),
                _t("about.doc_missing", filename=filename),
            )
            return False

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Error reading bundled document %s: %s", path, exc)
            QMessageBox.warning(
                parent,
                _t("common.error"),
                _t("about.doc_missing", filename=filename),
            )
            return False

        dialog = cls(title=title, text=content, parent=parent)
        dialog.exec()
        return True
