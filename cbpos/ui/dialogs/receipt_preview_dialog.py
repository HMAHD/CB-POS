from typing import List, Dict, Any
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
)

from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget
from cbpos.i18n import _t


class ReceiptPreviewDialog(QDialog):
    """Dialog to preview the receipt as it would appear on a thermal printer."""

    def __init__(self, commands: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("receipt_preview.title"))
        self.setFixedSize(400, 600)
        self._init_ui()
        self._preview.set_commands(commands)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self._preview = ReceiptPreviewWidget()
        layout.addWidget(self._preview, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton(_t("common.close"))
        btn_close.setProperty("class", "accent")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
