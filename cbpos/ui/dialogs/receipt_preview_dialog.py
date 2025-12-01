from typing import List, Dict, Any
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QLabel,
)
from PyQt6.QtCore import Qt


class ReceiptPreviewDialog(QDialog):
    """
    Dialog to preview the receipt as it would appear on a thermal printer.
    """

    def __init__(self, commands: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.commands = commands
        self.setWindowTitle("Receipt Preview")
        self.setFixedSize(400, 600)
        self._init_ui()
        self._render_receipt()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        lbl_title = QLabel("Thermal Receipt Preview (80mm)")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("font-weight: bold; color: #888;")
        layout.addWidget(lbl_title)

        # Preview Area
        self.preview_area = QTextBrowser()
        self.preview_area.setProperty("class", "preview-browser")
        layout.addWidget(self.preview_area)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)

        self.btn_print = QPushButton("Close Preview")
        self.btn_print.setStyleSheet("background-color: #00BCEB; color: white; font-weight: bold;")
        self.btn_print.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_print)
        layout.addLayout(btn_layout)

    def _render_receipt(self):
        # Get colors from config or defaults
        bg_color = "#FFFFFF"
        text_color = "#000000"

        html = [
            "<html><head><style>",
            "body { background-color: %s; color: %s; "
            "font-family: 'Courier New', monospace; font-size: 12px; }" % (bg_color, text_color),
            ".receipt-container { width: 300px; margin: 0 auto; }",
            ".center-block { display: block; text-align: center; }",
            ".cut-line { border-top: 1px dashed #000; margin: 10px 0; }",
            ".cut-text { text-align: center; font-size: 10px; color: #888; }",
            ".barcode-box { text-align: center; margin: 10px 0; " "border: 1px solid #000; padding: 5px; }",
            ".img-responsive { max-width: 100%; height: auto; }",
            "</style></head><body>",
            "<div class='receipt-container'>",
        ]

        for cmd in self.commands:
            c_type = cmd.get("type")
            align = cmd.get("align", "left")

            # CSS alignment
            style = "text-align: {};".format(align)
            if align == "center":
                style += " display: block;"

            if c_type == "text":
                val = cmd.get("val", "").replace(" ", "&nbsp;")
                val = val.replace("\n", "<br>")
                div = "<div style='{} white-space: pre-wrap;'>{}</div>".format(style, val)
                html.append(div)

            elif c_type == "image":
                path = cmd.get("path")
                if path:
                    # Use file:// protocol for local images
                    img_tag = (
                        "<div style='text-align: center;'>" "<img src='file:///{}' class='img-responsive'></div>"
                    ).format(path)
                    html.append(img_tag)

            elif c_type == "barcode":
                val = cmd.get("val")
                # Simulate barcode with a placeholder or simple div
                barcode_div = "<div class='barcode-box'>" f"[BARCODE: {val}]</div>"
                html.append(barcode_div)

            elif c_type == "feed":
                lines = cmd.get("lines", 1)
                html.append("<br>" * lines)

            elif c_type == "cut":
                html.append("<hr class='cut-line'>")
                html.append("<div class='cut-text'>[CUT]</div>")

        html.append("</div></body></html>")
        self.preview_area.setHtml("".join(html))
