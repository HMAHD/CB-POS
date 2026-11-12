"""Dialog and widget for previewing a barcode label before printing (#819).

Renders a realistic thermal-label mockup using real barcodes from python-barcode
and localized product names. Consumes the unified LabelLayout from LabelService.
"""

from typing import Any

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.label_service import LabelLayout, LabelOptions, LabelService
from cbpos.i18n import _t

# Default preview card dimensions (aspect ratio scales with mm dimensions)
PREVIEW_BASE_W = 280


class LabelCard(QWidget):
    """Paints a realistic thermal-label preview matching the unified LabelLayout."""

    def __init__(self, layout: LabelLayout | Any = None, parent=None) -> None:
        """Initialize the label card widget."""
        super().__init__(parent)
        self.setObjectName("LabelCard")
        self._layout: LabelLayout | None = None
        self._barcode_pixmap: QPixmap | None = None

        if isinstance(layout, LabelLayout):
            self.set_layout(layout)
        elif layout is not None:
            # Legacy Product passed directly
            self.set_layout(LabelService.create_layout(layout))
        else:
            self.setFixedSize(PREVIEW_BASE_W, 175)

    def set_layout(self, layout: LabelLayout) -> None:
        """Update the rendered label layout and re-render barcode."""
        self._layout = layout
        w_mm = max(25.0, layout.options.width_mm)
        h_mm = max(15.0, layout.options.height_mm)
        card_w = PREVIEW_BASE_W
        card_h = int(card_w * (h_mm / w_mm))
        card_h = max(140, min(240, card_h))
        self.setFixedSize(card_w, card_h)

        # Generate real barcode pixmap
        self._barcode_pixmap = None
        if layout.barcode_value:
            png_bytes = LabelService.render_barcode_image(layout.barcode_value, layout.barcode_symbology)
            if png_bytes:
                img = QImage()
                img.loadFromData(QByteArray(png_bytes))
                self._barcode_pixmap = QPixmap.fromImage(img)

        self.update()

    def paintEvent(self, event) -> None:
        """Paint the thermal label mockup: product name, barcode, barcode text, and price."""
        if self._layout is None:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        layout = self._layout

        # --- White label background with subtle paper gradient ---
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#FFFFFF"))
        grad.setColorAt(1.0, QColor("#F8F8F5"))
        p.setBrush(grad)
        p.setPen(QPen(QColor("#D0D0D0"), 1))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 6, 6)

        ink = QColor("#1A1A1A")
        sub_ink = QColor("#555555")

        # --- Product name(s) ---
        y_cursor = 8
        name_font = QFont()
        name_font.setPixelSize(13 if layout.secondary_name else 14)
        name_font.setWeight(QFont.Weight.Bold)
        p.setFont(name_font)
        p.setPen(ink)

        name_rect = QRectF(8, y_cursor, w - 16, 20)
        p.drawText(name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, layout.product_name)
        y_cursor += 20

        if layout.secondary_name:
            sec_font = QFont()
            sec_font.setPixelSize(12)
            p.setFont(sec_font)
            p.setPen(sub_ink)
            sec_rect = QRectF(8, y_cursor, w - 16, 18)
            p.drawText(sec_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, layout.secondary_name)
            y_cursor += 18

        # Separator line
        y_cursor += 2
        p.setPen(QPen(QColor("#E2E2E2"), 1))
        p.drawLine(16, y_cursor, w - 16, y_cursor)
        y_cursor += 4

        # --- Barcode image ---
        bar_h = max(30, min(55, int(h * 0.28)))
        if self._barcode_pixmap and not self._barcode_pixmap.isNull():
            bc_w = min(w - 32, max(120, int(w * 0.82)))
            bc_x = (w - bc_w) / 2
            bc_rect = QRectF(bc_x, y_cursor, bc_w, bar_h)
            p.drawPixmap(
                bc_rect.toRect(),
                self._barcode_pixmap.scaled(
                    bc_rect.size().toSize(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
        y_cursor += bar_h + 2

        # --- Barcode text ---
        code_font = QFont("Courier New")
        code_font.setPixelSize(11)
        code_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        p.setFont(code_font)
        p.setPen(QColor("#444444"))
        code_rect = QRectF(8, y_cursor, w - 16, 16)
        p.drawText(code_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, layout.barcode_value)
        y_cursor += 16

        # Separator line
        p.setPen(QPen(QColor("#E2E2E2"), 1))
        p.drawLine(16, y_cursor, w - 16, y_cursor)
        y_cursor += 3

        # --- Price text ---
        price_font = QFont()
        price_font.setPixelSize(18)
        price_font.setWeight(QFont.Weight.Bold)
        p.setFont(price_font)
        p.setPen(ink)
        price_rect = QRectF(8, y_cursor, w - 16, max(22, h - y_cursor - 4))
        p.drawText(price_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, layout.price_text)

        p.end()


# Backward compatibility alias
_LabelCard = LabelCard


class LabelPreviewDialog(QDialog):
    """Dialog showing a realistic thermal-label preview."""

    def __init__(self, product: Any, options: LabelOptions | None = None, parent=None) -> None:
        """Initialize the dialog and build header, label preview card, and close button."""
        super().__init__(parent)
        self.setWindowTitle(_t("label_preview.title"))
        self.setObjectName("LabelPreviewDialog")
        self.setMinimumSize(360, 340)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        self.label_layout = LabelService.create_layout(product, options)

        header = QLabel(self.label_layout.product_name)
        header.setObjectName("LabelPreviewHeader")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        card = LabelCard(self.label_layout)
        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        hint = QLabel(_t("label_preview.hint"))
        hint.setObjectName("LabelPreviewHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton(_t("common.close"))
        btn_close.setObjectName("BtnCancel")
        btn_close.setProperty("class", "secondary")
        btn_close.setMinimumHeight(44)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
