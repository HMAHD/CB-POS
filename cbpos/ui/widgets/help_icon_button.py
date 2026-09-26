"""Small info-icon affordance for a field a non-technical shop owner
might not know how to fill in.

Extracted from the Shop Info -> Email tab's SMTP help icon, which paired
a hover tooltip with a real 4-step setup guide dialog on click -- a
genuinely useful pattern this app had exactly one instance of, even
though several other fields (Purchasing's Payment Terms, Price Lists'
date ranges, Sales Tax's own VAT/SSCL fields) are just as unfamiliar to
a non-technical user (#318).
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QPushButton, QToolTip

from cbpos.config import Config


class HelpIconButton(QPushButton):
    """A small circular info-icon button with a tooltip and, optionally,
    a click handler that opens a guide dialog.

    Pass ``on_click`` (e.g. a method that builds a guide dialog and calls
    ``exec()`` on it, as the SMTP setup guide already does) for a field
    complex enough to need step-by-step help; omit it for a tooltip-only hint.
    """

    def __init__(self, tooltip: str = "", on_click=None, parent=None) -> None:
        """Create the circular info-icon button.

        Args:
            tooltip: Hover/tap hint text; shown on tap when *on_click* is omitted.
            on_click: Optional handler, e.g. one that opens a step-by-step guide dialog.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        info_icon_path = str(Config.BASE_DIR / "cbpos" / "assets" / "icons" / "info-circle-cyan.svg")
        self.setIcon(QIcon(info_icon_path))
        self.setIconSize(QSize(24, 24))
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("BtnInfoIcon")
        if tooltip:
            self.setToolTip(tooltip)
        if on_click:
            self.clicked.connect(on_click)
        else:
            # A hover-only tooltip never appears on a touchscreen POS
            # terminal -- tapping is the only gesture available there, so
            # a tooltip-only button (no on_click guide dialog) needs to
            # also show its tooltip on tap, or it does nothing when
            # clicked.
            self.clicked.connect(self._show_tooltip_on_click)

    def _show_tooltip_on_click(self) -> None:
        if self.toolTip():
            QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), self.toolTip(), self)
