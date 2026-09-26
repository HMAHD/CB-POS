"""Reusable receipt preview widget that simulates thermal paper output.

Renders device-agnostic receipt commands (from ``ReceiptBuilder``) into an
accurate HTML representation of what the printed receipt will look like.
Used inline in the Receipt Settings page and inside ``ReceiptPreviewDialog``.

**Qt constraint:** QTextBrowser uses Qt's rich-text engine (HTML 4 / CSS 2.1
subset).  It does NOT support flexbox, CSS gradients, box-shadow, or any
CSS 3 layout.

**Separator edge-to-edge trick:** Each separator closes the current content
``<td>``, inserts a full-width ``<tr>`` with a black-background cell, then
re-opens a new content ``<td>``.  This guarantees the line physically spans
the entire paper table width with zero gaps.
"""

import base64
import hashlib
import io
import logging
from html import escape
from typing import Any

from PIL import Image, UnidentifiedImageError
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

from cbpos.core.utils.thermal_image import dither_for_thermal_print
from cbpos.i18n import _t

logger = logging.getLogger(__name__)

# Body background -- neutral grey so white paper stands out.
_CSS = "body { margin: 0; padding: 0; background: #c8c8c8; }"

# Inline style applied to every text element for consistent monospace rendering.
_FONT = "font-family:'Courier New',Courier,monospace;font-size:11.5px;line-height:1.4;color:#000;"

# Horizontal padding applied to content elements (NOT the paper <td>).
_PX = 10


class ReceiptPreviewWidget(QWidget):
    """Thermal-paper receipt preview rendered via HTML inside a ``QTextBrowser``.

    Public API
    ----------
    set_commands(commands)  -- update the displayed receipt.
    set_paper_width(width)  -- "80mm" or "58mm"; adjusts container px width.
    """

    _PAPER_PX = {"80mm": 302, "58mm": 220}
    _CHAR_COLS = {"80mm": 42, "58mm": 32}

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create an empty 80mm preview; call ``set_commands()`` to render a receipt."""
        super().__init__(parent)
        self._commands: list[dict[str, Any]] = []
        self._paper_width = "80mm"
        self._init_ui()

    # Extra width beyond the paper's own pixel width, split evenly as a
    # visible grey margin on each side of the white paper -- without this
    # the browser's edge would touch the paper's edge exactly, with no
    # "resting on a surface" look.
    _BROWSER_MARGIN_PX = 40

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        # A containing QScrollArea with setWidgetResizable(True) stretches
        # this widget to fill its whole viewport whenever that viewport is
        # taller than the receipt -- without pinning to the top, this
        # layout would center the title+paper in that surplus height,
        # leaving an odd empty gap above them instead of just blank space
        # below (which is what an unused scroll area normally looks like).
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._lbl_title = QLabel(_t("receipt_preview.title"))
        self._lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_title.setObjectName("ReceiptPreviewTitle")
        layout.addWidget(self._lbl_title)

        self._browser = QTextBrowser()
        self._browser.setObjectName("ReceiptPreviewBrowser")
        self._browser.setOpenExternalLinks(False)
        # The browser is resized to fit its whole document (see
        # _resize_to_content) instead of scrolling internally, so a
        # scrollbar should never actually be needed -- but disable both
        # explicitly rather than merely relying on that always holding,
        # since an internal scrollbar reserves layout space the instant
        # it appears, throwing off the centered-paper width math.
        self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Force black text -- QTextBrowser ignores inline CSS color and uses
        # the widget palette.  Set both palette AND document stylesheet so
        # black text survives any QSS theme override.
        pal = self._browser.palette()
        pal.setColor(QPalette.ColorRole.Text, QColor("#000000"))
        self._browser.setPalette(pal)
        self._browser.document().setDefaultStyleSheet("body { color: #000000; } b { color: #000000; }")
        # Eliminate default document margin so our table fills the viewport.
        self._browser.document().setDocumentMargin(0)
        # Fixed width matching the paper size (updated in set_paper_width)
        # instead of stretching to fill whatever space the parent layout
        # gives this widget -- otherwise the grey "surface" behind the
        # paper stays a large fixed box regardless of paper width, with
        # the paper floating in the middle of it looking unfinished.
        self._browser.setFixedWidth(self._target_browser_width())
        layout.addWidget(self._browser, 0, Qt.AlignmentFlag.AlignHCenter)
        # An explicit stretch item, not just setAlignment(AlignTop) above --
        # a containing QScrollArea's setWidgetResizable(True) stretches
        # this widget to fill its whole viewport when the receipt is
        # shorter than it, and only a real stretch item reliably claims
        # that surplus instead of Qt handing it to the fixed-height
        # browser anyway and pushing it away from the top.
        layout.addStretch()

    def set_commands(self, commands: list[dict[str, Any]]) -> None:
        """Replace the current receipt with *commands* and re-render."""
        self._commands = commands or []
        self._render()

    def set_paper_width(self, width: str) -> None:
        """Set paper width ("80mm" or "58mm") and re-render."""
        if width not in self._PAPER_PX:
            width = "80mm"
        if width != self._paper_width:
            self._paper_width = width
            self._lbl_title.setText(_t("receipt_preview.title") + f" ({width})")
            self._browser.setFixedWidth(self._target_browser_width())
            self._render()

    def _target_browser_width(self) -> int:
        """Browser width for the current paper size plus a fixed side margin.

        No scrollbar-space compensation needed -- the browser never
        scrolls internally (see _resize_to_content), so its full width is
        always just the paper plus its resting margin.
        """
        return self._PAPER_PX[self._paper_width] + self._BROWSER_MARGIN_PX

    def _resize_to_content(self) -> None:
        """Grow the browser's height to fit its whole document.

        Without this, the browser keeps whatever height its parent layout
        happens to hand it and scrolls internally to show the rest of a
        tall receipt -- cramming the preview into a small window-within-
        a-window instead of just showing the full paper (the outer page
        already scrolls for content taller than the window, same as
        every other settings tab).
        """
        doc = self._browser.document()
        doc.setTextWidth(self._browser.width())
        self._browser.setFixedHeight(int(doc.size().height()) + 4)

    def _render(self) -> None:
        """Convert the command list into styled HTML and display it."""
        px = self._PAPER_PX[self._paper_width]
        cols = self._CHAR_COLS[self._paper_width]

        parts: list[str] = [
            f"<html><head><style>{_CSS}</style></head><body>",
            "<div style='height:8px;font-size:1px;'>&nbsp;</div>",
            "<table width='%d' cellpadding='0' cellspacing='0'"
            " bgcolor='#ffffff' align='center'>"
            "<tr><td style='padding:12px 0 0;%s'>" % (px, _FONT),
        ]

        for cmd in self._commands:
            self._render_command(cmd, cols, parts, self._paper_width)

        parts.append("</td></tr></table>")
        parts.append("<div style='height:8px;font-size:1px;'>&nbsp;</div>")
        parts.append("</body></html>")
        self._browser.setHtml("".join(parts))
        self._resize_to_content()

    @staticmethod
    def _render_command(
        cmd: dict[str, Any],
        cols: int,
        parts: list,
        paper_width: str = "80mm",
    ) -> None:
        """Render a single receipt command into HTML and append to *parts*."""
        ctype = cmd.get("type", "")
        bold = cmd.get("bold", False)
        p = _PX  # horizontal padding for content

        if ctype == "text":
            raw = cmd.get("val", "")
            stripped = raw.strip()

            # Full-width separator -- close the content cell, add a
            # full-width black row, then re-open a new content cell.
            # This guarantees the line goes from absolute left edge to
            # absolute right edge of the paper with zero gaps.
            if stripped and len(stripped) >= cols - 2 and set(stripped) <= {"-", "="}:
                parts.append(
                    "</td></tr>"
                    "<tr><td style='padding:4px 0;'>"
                    "<table width='100%' cellpadding='0' cellspacing='0'>"
                    "<tr><td bgcolor='#000000' style='height:1px;"
                    "font-size:1px;line-height:1px;'>"
                    "&nbsp;</td></tr></table>"
                    "</td></tr>"
                    f"<tr><td style='padding:0;{_FONT}'>"
                )
                return

            # Two-column split row (content gets horizontal padding)
            left_val = cmd.get("left_val")
            right_val = cmd.get("right_val")
            if left_val is not None or right_val is not None:
                lv = escape(left_val or "")
                rv = escape(right_val or "")
                if bold:
                    lv = f"<b>{lv}</b>" if lv else lv
                    rv = f"<b>{rv}</b>" if rv else rv
                parts.append(
                    "<table width='100%%' cellpadding='0' cellspacing='0'>"
                    "<tr>"
                    "<td style='padding:1px %dpx;text-align:left;%s'>"
                    "%s</td>"
                    "<td style='padding:1px %dpx;text-align:right;"
                    "white-space:nowrap;%s'>%s</td>"
                    "</tr></table>" % (p, _FONT, lv, p, _FONT, rv)
                )
                return

            # Plain text line (content gets horizontal padding).
            align = cmd.get("align", "left")
            val = escape(raw).replace("\n", "<br>")
            if bold:
                val = f"<b>{val}</b>"
            parts.append(
                "<div align='%s' style='margin:0;padding:1px %dpx;"
                "%stext-align:%s;'>%s</div>" % (align, p, _FONT, align, val)
            )

        elif ctype == "image":
            path = cmd.get("path", "")
            if path:
                data_uri = _dithered_logo_data_uri(path, paper_width)
                if data_uri:
                    parts.append(
                        "<div align='center' style='text-align:center;"
                        "margin:4px 0;padding:0 %dpx;'>"
                        "<img src='%s'"
                        " style='max-width:100%%;height:auto;'></div>" % (p, data_uri)
                    )

        elif ctype == "barcode":
            val = cmd.get("val", "")
            if val and cmd.get("code") == "QR":
                # Unlike the 1D barcode below, this is a real, scannable QR
                # (#328) -- generated the same way it will actually print,
                # so no "preview only" caveat is needed here.
                data_uri = _qr_code_data_uri(val)
                if data_uri:
                    parts.append(
                        "<div align='center' style='text-align:center;"
                        f"margin:6px 0 2px;'><img src='{data_uri}' width='120' height='120'></div>"
                    )
            elif val:
                barcode_html = _generate_barcode_bars(val)
                parts.append(
                    "<div align='center' style='text-align:center;padding:6px %dpx 2px;'>%s</div>" % (p, barcode_html)
                )
                parts.append(
                    "<div align='center' style='text-align:center;"
                    "padding:0 %dpx 4px;font-size:9px;color:#000;"
                    "%s'>%s</div>" % (p, _FONT, escape(val))
                )
                # This rendering is decorative bars derived from a hash of
                # the value, not a real barcode encoding -- it can never be
                # scanned, so nothing here validates real print quality
                # (#329).
                parts.append(
                    "<div align='center' style='text-align:center;"
                    "padding:0 %dpx 6px;font-size:8px;color:#999;"
                    "font-style:italic;%s'>%s</div>" % (p, _FONT, escape(_t("receipt_preview.barcode_not_scannable")))
                )

        elif ctype == "feed":
            lines = cmd.get("lines", 1)
            for _ in range(lines):
                parts.append("<div style='height:5px;font-size:1px;'>&nbsp;</div>")

        elif ctype == "cut":
            # Close cell, add separator row, re-open cell for cut label.
            parts.append(
                "</td></tr>"
                "<tr><td style='padding:4px 0;'>"
                "<table width='100%' cellpadding='0' cellspacing='0'>"
                "<tr><td bgcolor='#000000' style='height:1px;"
                "font-size:1px;line-height:1px;'>"
                "&nbsp;</td></tr></table>"
                "</td></tr>"
                f"<tr><td style='padding:0;{_FONT}'>"
            )
            parts.append(
                "<div align='center' style='text-align:center;"
                "font-size:8px;color:#999;padding:0;margin:0;'>"
                "&#9986; cut</div>"
            )


def _dithered_logo_data_uri(path: str, paper_width: str) -> str:
    """Return the logo as a base64 PNG data URI, converted to the real 1-bit
    thermal output the printer will produce (see thermal_image.py).

    Embedding a processed data URI instead of an ``img src='file:///...'``
    link to the raw file means the preview shows what will actually print
    -- a full-color/greyscale logo that looks fine in the file picker can
    turn into an unreadable grey blob once naively converted to monochrome,
    which a shop owner would otherwise only discover after wasting real
    receipt paper (#330). Returns "" if the file can't be read as an image
    so a bad/missing logo path just omits the image instead of crashing
    the preview.
    """
    try:
        with Image.open(path) as source:
            dithered = dither_for_thermal_print(source, paper_width)
            buffer = io.BytesIO()
            dithered.convert("L").save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
    except (OSError, UnidentifiedImageError) as e:
        logger.warning("Could not render logo preview for %s: %s", path, e)
        return ""


def _qr_code_data_uri(content: str) -> str:
    """Return a real, scannable QR code (encoding *content*) as a base64
    PNG data URI -- generated by the same ``qrcode`` library the app
    already depends on, so what's shown here is genuinely what a phone
    would scan, not a decorative approximation like the 1D barcode
    preview below (#328). Returns "" if generation fails so a bad value
    just omits the code instead of crashing the preview.
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage

        img = qrcode.make(content, image_factory=PilImage)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception as e:
        logger.warning("Could not render QR code preview: %s", e)
        return ""


def _generate_barcode_bars(value: str) -> str:
    """Generate a visual barcode pattern using HTML table cells.

    Creates alternating black and white bars of varying widths derived
    from a hash of the value.  This is purely decorative -- it is NOT
    scannable but looks like a barcode in the preview.
    """
    if not value:
        return ""
    # Use hash to generate a deterministic bar pattern.
    h = hashlib.md5(value.encode()).hexdigest()
    cells: list[str] = []
    for i, ch in enumerate(h[:28]):
        n = int(ch, 16)
        # Alternate black/white; width 1-3px based on hex digit.
        is_black = i % 2 == 0
        w = (n % 3) + 1
        color = "#000" if is_black else "#fff"
        cells.append("<td bgcolor='%s' style='width:%dpx;height:32px;font-size:1px;'>&nbsp;</td>" % (color, w))
    return "<table cellpadding='0' cellspacing='0' align='center'><tr>{}</tr></table>".format("".join(cells))
