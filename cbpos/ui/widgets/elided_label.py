"""A QLabel that elides its text to fit its current width instead of
letting it silently overflow past its container's edge.

The action panel's customer name/phone field had no truncation at all:
a long name pushed the phone number past the card's edge, hard-clipped
by the layout with no visual indication there was more text, and no
way to read the missing part. This keeps the full string available via
a tooltip and re-elides on every resize, since the panel's width is
itself resizable (280-400px).
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._full_text = ""

    def setText(self, text: str) -> None:  # noqa: N802 (Qt override)
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._apply_elided_text()

    def text(self) -> str:  # noqa: N802 (Qt override)
        """Return the real, un-elided text -- not what's currently painted."""
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._apply_elided_text()

    def _apply_elided_text(self) -> None:
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        super().setText(elided)
