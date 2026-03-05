"""Reusable receipt preview widget that simulates thermal paper output.

Renders device-agnostic receipt commands (from ``ReceiptBuilder``) into an
accurate HTML representation of what the printed receipt will look like.
Used inline in the Receipt Settings page and inside ``ReceiptPreviewDialog``.
"""

from html import escape
from typing import List, Dict, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QLabel, QTextBrowser


class ReceiptPreviewWidget(QWidget):
    """Thermal-paper receipt preview rendered via HTML inside a ``QTextBrowser``.

    Public API
    ----------
    set_commands(commands)  – update the displayed receipt.
    set_paper_width(width)  – "80mm" or "58mm"; adjusts container px width.
    """

    # Pixel widths that approximate real paper proportions on screen.
    _PAPER_PX = {"80mm": 302, "58mm": 220}
    _CHAR_COLS = {"80mm": 42, "58mm": 32}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commands: List[Dict[str, Any]] = []
        self._paper_width = "80mm"
        self._init_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
            self._lbl_title.setText(f"Receipt Preview ({width})")
            self._render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        """Convert the command list into styled HTML and display it."""
        px = self._PAPER_PX[self._paper_width]
        cols = self._CHAR_COLS[self._paper_width]

        css = (
            "body{margin:0;padding:0;background:#F5F5F0;}"
            ".paper{"
            f"width:{px}px;margin:12px auto;padding:18px 14px;"
            "background:#fff;color:#000;"
            "font-family:'Courier New',Courier,monospace;font-size:11.5px;"
            "line-height:1.45;letter-spacing:0.2px;"
            "box-shadow:0 2px 12px rgba(0,0,0,0.15);"
            "border-radius:2px;"
            "}"
            ".dash{border:none;border-top:1px dashed #000;margin:6px 0;}"
            ".cut{border:none;border-top:2px dashed #999;margin:8px 0;}"
            ".cut-lbl{text-align:center;font-size:9px;color:#999;margin:2px 0 4px;}"
            ".bc{text-align:center;margin:8px 0;padding:6px;"
            "font-family:'Libre Barcode 39','IDAutomationHC39M',monospace;"
            "font-size:32px;letter-spacing:2px;}"
            ".qr{text-align:center;margin:8px 0;padding:8px;"
            "border:1px solid #ccc;border-radius:4px;font-size:10px;color:#555;}"
            ".img-c{text-align:center;margin:4px 0;}"
            ".img-c img{max-width:100%;height:auto;}"
        )

        parts: list[str] = [
            "<html><head><style>",
            css,
            "</style></head><body><div class='paper'>",
        ]

        for cmd in self._commands:
            ctype = cmd.get("type", "")
            align = cmd.get("align", "left")
            style = f"text-align:{align};"

            if ctype == "text":
                val = escape(cmd.get("val", ""))
                # Preserve monospace alignment: replace spaces with &nbsp;
                val = val.replace(" ", "&nbsp;")
                val = val.replace("\n", "<br>")
                # Detect full-width dash separators
                raw = cmd.get("val", "")
                if raw and len(raw) >= cols and set(raw.strip()) <= {"-", "="}:
                    parts.append("<hr class='dash'>")
                else:
                    parts.append(
                        f"<div style='{style} white-space:pre-wrap;'>{val}</div>"
                    )

            elif ctype == "image":
                path = cmd.get("path", "")
                if path:
                    parts.append(
                        f"<div class='img-c'>"
                        f"<img src='file:///{escape(path)}'></div>"
                    )

            elif ctype == "barcode":
                val = escape(cmd.get("val", ""))
                code = cmd.get("code", "CODE39")
                if code == "QR":
                    parts.append(
                        f"<div class='qr'>&#9638; QR: {val} &#9638;</div>"
                    )
                else:
                    # Render with barcode font if available, fallback to text
                    parts.append(
                        f"<div class='bc'>*{val}*</div>"
                        f"<div style='text-align:center;font-size:9px;'>{val}</div>"
                    )

            elif ctype == "feed":
                lines = cmd.get("lines", 1)
                parts.append("<br>" * lines)

            elif ctype == "cut":
                parts.append("<hr class='cut'>")
                parts.append("<div class='cut-lbl'>&#9986; cut</div>")

        parts.append("</div></body></html>")
        self._browser.setHtml("".join(parts))
