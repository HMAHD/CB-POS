"""Render receipt text lines the printer's code pages can't encode as images.

ESC/POS printers only have built-in fonts for Latin-style code pages:
python-escpos sends every Sinhala or Tamil character as "?". So a receipt
in Sinhala/Tamil (receipt language, or the shop's own header/footer text)
would print as rows of question marks. Such lines are drawn with Qt --
which shapes Sinhala/Tamil properly with the bundled Noto fonts, the same
fonts the receipt preview uses -- and sent to the printer as a 1-bit
image instead (#625). Plain English lines stay text: faster and crisper.

Qt can paint into a QImage from a worker thread, so this runs on the
PrintWorker thread, never the UI thread.
"""

from PIL import Image
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from cbpos.core.utils.thermal_image import PAPER_DOT_WIDTH

# Unicode blocks with no ESC/POS code page: Tamil, Sinhala.
_RASTER_RANGES = ((0x0B80, 0x0BFF), (0x0D80, 0x0DFF))

_FONT_FAMILIES = ["Noto Sans Sinhala", "Noto Sans Tamil", "Noto Sans"]
_PIXEL_SIZE = 24  # ~ the printer's own 12x24 font height
_MIN_PIXEL_SIZE = 14
_PADDING = 2
_THRESHOLD = 160  # grey levels above this become white paper


def needs_raster(text: str) -> bool:
    """True if *text* has characters the printer can't print as text (Sinhala/Tamil)."""
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in _RASTER_RANGES)


def _font(bold: bool, pixel_size: int) -> QFont:
    font = QFont()
    font.setFamilies(_FONT_FAMILIES)
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    return font


def render_text_line(command: dict, paper_width: str = "80mm") -> Image.Image:
    """Draw one builder text command as a black-on-white 1-bit image.

    Two-column rows (``left_val``/``right_val``) keep the label on the left
    and the amount on the right; other lines follow ``align``. Text too
    wide for the paper is drawn smaller rather than cut off.

    Args:
        command: A ``{"type": "text", ...}`` receipt command.
        paper_width: "58mm" or "80mm" -- sets the image width in dots.

    Returns:
        A mode "1" PIL image exactly the paper's dot width wide.
    """
    width = PAPER_DOT_WIDTH.get(paper_width, PAPER_DOT_WIDTH["80mm"])
    bold = bool(command.get("bold"))
    left, right = command.get("left_val"), command.get("right_val")
    two_col = left is not None and right is not None
    text = command.get("val", "") if not two_col else f"{left}  {right}"

    pixel_size = _PIXEL_SIZE
    font = _font(bold, pixel_size)
    while pixel_size > _MIN_PIXEL_SIZE and QFontMetrics(font).horizontalAdvance(text) > width:
        pixel_size -= 1
        font = _font(bold, pixel_size)
    height = QFontMetrics(font).height() + 2 * _PADDING

    canvas = QImage(width, height, QImage.Format.Format_Grayscale8)
    canvas.fill(QColor("white"))
    painter = QPainter(canvas)
    try:
        painter.setFont(font)
        painter.setPen(QColor("black"))
        box = QRect(0, _PADDING, width, height - 2 * _PADDING)
        vcenter = Qt.AlignmentFlag.AlignVCenter
        if two_col:
            painter.drawText(box, Qt.AlignmentFlag.AlignLeft | vcenter, left)
            painter.drawText(box, Qt.AlignmentFlag.AlignRight | vcenter, right)
        else:
            align = {
                "center": Qt.AlignmentFlag.AlignHCenter,
                "right": Qt.AlignmentFlag.AlignRight,
            }.get(str(command.get("align", "left")).lower(), Qt.AlignmentFlag.AlignLeft)
            painter.drawText(box, align | vcenter, text)
    finally:
        painter.end()

    raw = canvas.constBits().asstring(canvas.sizeInBytes())
    grey = Image.frombuffer("L", (width, height), raw, "raw", "L", canvas.bytesPerLine(), 1)
    return grey.point(lambda p: 255 if p > _THRESHOLD else 0).convert("1")
