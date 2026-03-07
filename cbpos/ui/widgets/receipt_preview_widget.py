"""Reusable receipt preview widget that simulates thermal paper output.

Renders device-agnostic receipt commands (from ``ReceiptBuilder``) into an
accurate HTML representation of what the printed receipt will look like.
Used inline in the Receipt Settings page and inside ``ReceiptPreviewDialog``.

**Qt constraint:** QTextBrowser uses Qt's rich-text engine (HTML 4 / CSS 2.1
subset).  It does NOT support flexbox, CSS gradients, box-shadow, or any
CSS 3 layout.  ``<hr>`` tags have hardcoded internal margins that CSS cannot
override, so separators are rendered as monospace dash characters instead.
"""

from html import escape
from typing import List, Dict, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QLabel, QTextBrowser

# Only body background — everything else uses inline styles on elements
# to avoid QTextBrowser's unreliable CSS class inheritance.
_CSS = "body { margin: 0; padding: 0; background: #d0d0d0; }"

# Inline style constants (reused across elements)
_FONT = "font-family:'Courier New',Courier,monospace;font-size:10.5px;line-height:1.3;"

# Unicode block characters for barcode simulation.
_BARCODE_CHARS = "\u2588\u258c\u2590\u2588\u2590\u258c\u2588\u258c\u2590\u2588\u258c\u2588\u2590\u258c\u2590\u2588"


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
        super().__init__(parent)
        self._commands: List[Dict[str, Any]] = []
        self._paper_width = "80mm"
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._lbl_title = QLabel("Receipt Preview")
        self._lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_title.setObjectName("ReceiptPreviewTitle")
        layout.addWidget(self._lbl_title)

        self._browser = QTextBrowser()
        self._browser.setObjectName("ReceiptPreviewBrowser")
        self._browser.setOpenExternalLinks(False)
        layout.addWidget(self._browser)

    def set_commands(self, commands: List[Dict[str, Any]]) -> None:
        """Replace the current receipt with *commands* and re-render."""
        self._commands = commands or []
        self._render()

    def set_paper_width(self, width: str) -> None:
        """Set paper width ("80mm" or "58mm") and re-render."""
        if width not in self._PAPER_PX:
            width = "80mm"
        if width != self._paper_width:
            self._paper_width = width
            self._lbl_title.setText("Receipt Preview (%s)" % width)
            self._render()

    def _render(self) -> None:
        """Convert the command list into styled HTML and display it."""
        px = self._PAPER_PX[self._paper_width]
        cols = self._CHAR_COLS[self._paper_width]

        # Paper = single-cell table with white background, centered.
        # All receipt content goes inside this one <td>.
        parts: list[str] = [
            "<html><head><style>%s</style></head><body>" % _CSS,
            "<table width='%d' cellpadding='0' cellspacing='0'"
            " bgcolor='#ffffff' align='center'"
            " style='%scolor:#000;'>"
            "<tr><td style='padding:10px 0 6px;'>" % (px, _FONT),
        ]

        for cmd in self._commands:
            self._render_command(cmd, cols, parts)

        parts.append("</td></tr></table></body></html>")
        self._browser.setHtml("".join(parts))

    @staticmethod
    def _render_command(
        cmd: Dict[str, Any],
        cols: int,
        parts: list,
    ) -> None:
        """Render a single receipt command into HTML and append to *parts*."""
        ctype = cmd.get("type", "")
        bold = cmd.get("bold", False)

        if ctype == "text":
            raw = cmd.get("val", "")
            stripped = raw.strip()

            # Full-width separator — render actual dash characters with NO
            # padding so they go edge-to-edge.  Never use <hr> in QTextBrowser
            # (it has hardcoded internal margins that CSS cannot override).
            if stripped and len(stripped) >= cols - 2 and set(stripped) <= {"-", "="}:
                # Use many more characters than needed; overflow:hidden clips
                # to the container width, guaranteeing edge-to-edge fill.
                char = stripped[0]
                fill = char * 200
                parts.append(
                    "<div style='padding:0;margin:0;%s" "overflow:hidden;white-space:nowrap;'>%s</div>" % (_FONT, fill)
                )
                return

            # Two-column split row (left/right alignment via table)
            left_val = cmd.get("left_val")
            right_val = cmd.get("right_val")
            if left_val is not None or right_val is not None:
                lv = escape(left_val or "")
                rv = escape(right_val or "")
                if bold:
                    lv = "<b>%s</b>" % lv if lv else lv
                    rv = "<b>%s</b>" % rv if rv else rv
                parts.append(
                    "<table width='100%%' cellpadding='0' cellspacing='0'><tr>"
                    "<td style='padding:0 8px;text-align:left;'>%s</td>"
                    "<td style='padding:0 8px;text-align:right;"
                    "white-space:nowrap;'>%s</td>"
                    "</tr></table>" % (lv, rv)
                )
                return

            # Plain text line (with 8px horizontal padding)
            align = cmd.get("align", "left")
            val = escape(raw).replace("\n", "<br>")
            if bold:
                val = "<b>%s</b>" % val
            parts.append("<div style='margin:0;padding:0 8px;%s" "text-align:%s;'>%s</div>" % (_FONT, align, val))

        elif ctype == "image":
            path = cmd.get("path", "")
            if path:
                parts.append(
                    "<div style='text-align:center;margin:2px 0;"
                    "padding:0 8px;'><img src='file:///%s'"
                    " style='max-width:100%%;height:auto;'></div>" % escape(path)
                )

        elif ctype == "barcode":
            val = escape(cmd.get("val", ""))
            # Barcode centered — Unicode block characters + label below
            parts.append(
                "<table width='100%%' cellpadding='0' cellspacing='0'>"
                "<tr><td style='text-align:center;padding:4px 8px;"
                "%sfont-size:12px;letter-spacing:1px;'>"
                "%s</td></tr>" % (_FONT, _BARCODE_CHARS)
            )
            if val:
                parts.append("<tr><td style='text-align:center;padding:0 8px;" "font-size:8px;'>%s</td></tr>" % val)
            parts.append("</table>")

        elif ctype == "feed":
            lines = cmd.get("lines", 1)
            for _ in range(lines):
                parts.append("<div style='height:4px;font-size:1px;'>&nbsp;</div>")

        elif ctype == "cut":
            # Render cut as grey dashes (same technique as separator)
            cut_fill = "- " * 100
            parts.append(
                "<div style='padding:4px 0 0;margin:0;%s"
                "color:#999;overflow:hidden;white-space:nowrap;'>"
                "%s</div>" % (_FONT, cut_fill.strip())
            )
            parts.append(
                "<div style='text-align:center;font-size:8px;"
                "color:#999;padding:0;margin:0 0 2px;'>"
                "&#9986; cut</div>"
            )
