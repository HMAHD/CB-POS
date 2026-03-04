"""
Dialog for previewing a barcode label before printing.
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QWidget, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QFont, QColor, QPen
from cbpos.core.models import Product
from cbpos.core.utils.formatters import format_currency


def _get_text_color() -> QColor:
    """Get text color appropriate for current theme."""
    from cbpos.core.services.theme_service import ThemeService

    return QColor("#1a1a2e") if ThemeService.current_theme.lower() == "light" else QColor("#e0e0e0")


class _LabelCanvas(QWidget):
    """Widget that paints a barcode label preview using QPainter."""

    def __init__(self, product: Product, parent=None) -> None:
        super().__init__(parent)
        self.product = product
        self.setFixedSize(300, 200)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        text_color = _get_text_color()
        w = self.width()
        h = self.height()

        # Border
        painter.setPen(QPen(text_color, 1))
        painter.drawRect(1, 1, w - 2, h - 2)

        # Product name (bold, centered)
        name_font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(name_font)
        painter.setPen(text_color)
        name_rect = QRectF(10, 10, w - 20, 30)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self.product.name_en)

        # Barcode bars (simplified visual representation)
        barcode = self.product.barcode or ""
        bar_y = 50
        bar_h = 50
        bar_area_w = w - 60
        bar_x_start = 30

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(text_color)

        # Generate pseudo-bars from barcode characters
        if barcode:
            num_bars = len(barcode) * 3 + 10  # approximate bar count
            bar_w = bar_area_w / max(num_bars, 1)
            x = bar_x_start
            for i, ch in enumerate(barcode):
                val = ord(ch) % 7
                # Draw alternating thick/thin bars
                for j in range(3):
                    bit = (val >> j) & 1
                    if bit or j == 1:
                        thickness = bar_w * 1.5 if bit else bar_w * 0.8
                        painter.drawRect(QRectF(x, bar_y, thickness, bar_h))
                    x += bar_w

        # Barcode text (centered below bars)
        code_font = QFont("Courier New", 9)
        painter.setFont(code_font)
        painter.setPen(text_color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        code_rect = QRectF(10, bar_y + bar_h + 5, w - 20, 20)
        painter.drawText(code_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, barcode)

        # Price (large, centered)
        price_font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        painter.setFont(price_font)
        price_text = format_currency(self.product.price)
        price_rect = QRectF(10, h - 50, w - 20, 40)
        painter.drawText(price_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, price_text)

        painter.end()


class LabelPreviewDialog(QDialog):
    """Dialog showing a visual preview of a barcode label."""

    def __init__(self, product: Product, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Label Preview — {product.name_en}")
        self.setObjectName("LabelPreviewDialog")
        self.setFixedSize(340, 260)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        canvas = _LabelCanvas(product)
        layout.addWidget(canvas, alignment=Qt.AlignmentFlag.AlignCenter)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
