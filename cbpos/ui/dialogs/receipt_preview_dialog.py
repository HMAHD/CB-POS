from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget


class ReceiptPreviewDialog(QDialog):
    """Dialog to preview the receipt as it would appear on a thermal printer."""

    def __init__(self, commands: list[dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("receipt_preview.title"))
        self.setFixedSize(400, 600)
        self._init_ui()
        self._preview.set_commands(commands)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # ReceiptPreviewWidget sizes its browser to the full receipt
        # height rather than scrolling internally -- a receipt with many
        # items easily exceeds this dialog's fixed 600px height, so this
        # scroll area is what actually lets the rest of it be reached.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._preview = ReceiptPreviewWidget()
        scroll.setWidget(self._preview)
        layout.addWidget(scroll, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton(_t("common.close"))
        btn_close.setProperty("class", "accent")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
