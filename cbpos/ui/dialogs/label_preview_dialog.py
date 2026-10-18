"""
Dialog for previewing a barcode label before printing.

Renders a realistic thermal-label mockup: white card with product name,
CODE128-style barcode bars, barcode text, and price.
"""

import hashlib

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.models import Product
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t

# Label card dimensions (mimics a 50x30mm thermal label at 2x)
LABEL_W = 300
LABEL_H = 190


def _code128_bars(barcode: str) -> list[tuple[float, bool]]:
    """Generate deterministic bar pattern from barcode string.

    Returns list of (width_ratio, is_bar) tuples that look like
    a realistic CODE128 barcode.  Uses a hash to spread bits evenly
    so the visual is convincing regardless of input length.
    """
    digest = hashlib.sha256(barcode.encode()).digest()
    bits: list[int] = []
    for byte in digest[:16]:
        for shift in range(8):
            bits.append((byte >> shift) & 1)

    # Quiet zone + start pattern
    bars: list[tuple[float, bool]] = [(4.0, False)]

    # Start code (fixed pattern)
    start = [2, 1, 1, 4, 1, 2]
    for idx, w in enumerate(start):
        bars.append((w * 0.7, idx % 2 == 0))

    # Data bars from hash
    for i in range(0, len(bits) - 1, 2):
        w = 1.0 + bits[i] * 0.8
        bars.append((w, True))
        gap = 0.6 + bits[i + 1] * 0.5
        bars.append((gap, False))

    # Stop pattern
    stop = [2, 3, 1, 1, 1, 2]
    for idx, w in enumerate(stop):
        bars.append((w * 0.7, idx % 2 == 0))

    bars.append((4.0, False))  # Quiet zone
    return bars


class _LabelCard(QWidget):
    """Paints a realistic thermal-label preview."""

    def __init__(self, product: Product, parent=None) -> None:
        """Initialize the label card widget for the given product."""
        super().__init__(parent)
        self.product = product
        self.setFixedSize(LABEL_W, LABEL_H)
        self.setObjectName("LabelCard")

    def paintEvent(self, event) -> None:
        """Paint the mock thermal label: product name, barcode bars, barcode text, and price."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # --- White label background with subtle paper gradient ---
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#FFFFFF"))
        grad.setColorAt(1.0, QColor("#F5F5F0"))
        p.setBrush(grad)
        p.setPen(QPen(QColor("#D0D0D0"), 1))
        p.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)

        ink = QColor("#1A1A1A")

        # --- Product name (bold, centered) ---
        name_font = QFont()
        name_font.setPixelSize(15)
        name_font.setWeight(QFont.Weight.Bold)
        p.setFont(name_font)
        p.setPen(ink)

        name_rect = QRectF(12, 10, w - 24, 24)
        p.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self.product.name_en,
        )

        # --- Thin separator ---
        p.setPen(QPen(QColor("#E0E0E0"), 1))
        p.drawLine(20, 38, w - 20, 38)

        # --- Barcode bars ---
        barcode = self.product.barcode or ""
        bar_y = 46
        bar_h = 56

        if barcode:
            bars = _code128_bars(barcode)
            total_w = sum(bw for bw, _ in bars)
            scale = (w - 40) / total_w
            x = 20.0

            p.setPen(Qt.PenStyle.NoPen)
            for bw, is_bar in bars:
                px_w = bw * scale
                if is_bar:
                    p.setBrush(ink)
                    p.drawRect(QRectF(x, bar_y, px_w, bar_h))
                x += px_w

        # --- Barcode text ---
        code_font = QFont("Courier New")
        code_font.setPixelSize(11)
        code_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        p.setFont(code_font)
        p.setPen(QColor("#444444"))
        p.setBrush(Qt.BrushStyle.NoBrush)

        code_rect = QRectF(12, bar_y + bar_h + 2, w - 24, 18)
        p.drawText(
            code_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            barcode,
        )

        # --- Thin separator ---
        sep_y = bar_y + bar_h + 22
        p.setPen(QPen(QColor("#E0E0E0"), 1))
        p.drawLine(20, sep_y, w - 20, sep_y)

        # --- Price (large, bold) ---
        price_font = QFont()
        price_font.setPixelSize(26)
        price_font.setWeight(QFont.Weight.Bold)
        p.setFont(price_font)
        p.setPen(ink)

        price_text = format_currency(self.product.price)
        price_rect = QRectF(12, sep_y + 4, w - 24, 36)
        p.drawText(
            price_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            price_text,
        )

        p.end()


class LabelPreviewDialog(QDialog):
    """Dialog showing a realistic thermal-label preview."""

    def __init__(self, product: Product, parent=None) -> None:
        """Initialize the dialog and build the header, label preview card, and close button."""
        super().__init__(parent)
        self.setWindowTitle(_t("label_preview.title"))
        self.setObjectName("LabelPreviewDialog")
        self.setFixedSize(360, 310)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # Header
        header = QLabel(product.name_en)
        header.setObjectName("LabelPreviewHeader")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Label card
        card = _LabelCard(product)
        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        # Footer hint
        hint = QLabel(_t("label_preview.hint"))
        hint.setObjectName("LabelPreviewHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton(_t("common.close"))
        btn_close.setObjectName("BtnCancel")
        btn_close.setProperty("class", "secondary")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
