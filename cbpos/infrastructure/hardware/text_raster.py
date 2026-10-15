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

The A4 invoice PDF has the same problem (ReportLab can't shape Sinhala or
Tamil), so ``render_text_png`` draws such text for it (#740).
"""

from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from cbpos.core.utils.text_scripts import needs_raster
from cbpos.core.utils.thermal_image import PAPER_DOT_WIDTH

__all__ = ["needs_raster", "render_text_line", "render_text_png"]

_FONT_FAMILIES = ["Noto Sans Sinhala", "Noto Sans Tamil", "Noto Sans"]
_PIXEL_SIZE = 24  # ~ the printer's own 12x24 font height
_MIN_PIXEL_SIZE = 14
_PADDING = 2
_THRESHOLD = 160  # grey levels above this become white paper


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


_PDF_DPI = 300  # A4-document text is drawn at print resolution


def render_text_png(
    text: str,
    point_size: float,
    bold: bool = False,
    color: str = "#000000",
    max_width_pt: float | None = None,
    align: str = "left",
) -> tuple[bytes, float, float]:
    """Draw *text* as a transparent PNG for a PDF page, shaped by Qt (#740).

    ReportLab can't shape Sinhala or Tamil (vowel signs land in the wrong
    place), so the A4 invoice places such text as an image drawn here with
    the same bundled Noto fonts. Text wider than *max_width_pt* wraps.

    Args:
        text: The text to draw.
        point_size: Font size in points.
        bold: Draw in bold.
        color: Text colour, as "#RRGGBB".
        max_width_pt: Wrap width in points; None keeps it on one line.
        align: "left", "center" or "right" within the wrap width.

    Returns:
        (PNG bytes, width in points, height in points).
    """
    scale = _PDF_DPI / 72
    font = _font(bold, max(1, round(point_size * scale)))
    metrics = QFontMetrics(font)
    flags = {
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
    }.get(align, Qt.AlignmentFlag.AlignLeft).value
    width = metrics.horizontalAdvance(text) + 2 * _PADDING
    if max_width_pt is not None and width > max_width_pt * scale:
        width = int(max_width_pt * scale)
        flags |= Qt.TextFlag.TextWordWrap.value
    height = metrics.boundingRect(QRect(0, 0, width, 100_000), flags, text).height() + 2 * _PADDING

    canvas = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    try:
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(QRect(0, _PADDING, width, height - 2 * _PADDING), flags, text)
    finally:
        painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    canvas.save(buffer, "PNG")
    return bytes(buffer.data()), width / scale, height / scale
