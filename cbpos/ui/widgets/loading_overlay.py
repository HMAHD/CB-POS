"""
Reusable loading overlay widget.

Displays a semi-transparent dark overlay with a spinning indicator
and optional status text.  Covers its parent widget entirely.

Usage::

    overlay = LoadingOverlay(parent_widget)
    overlay.show_loading("Generating report...")
    # ... when done:
    overlay.hide_loading()
"""

from PyQt6.QtCore import Qt, QTimer, QRectF, QEvent
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QWidget


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with animated spinner and optional text."""

    _ACCENT = QColor("#00BCEB")  # Cyan accent from Ceylon Byte theme
    _ARC_WIDTH = 4
    _SPINNER_RADIUS = 24
    _INTERVAL_MS = 30  # ~33 fps

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._angle: float = 0.0
        self._text: str = ""

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        if parent:
            parent.installEventFilter(self)

    # -- public API ----------------------------------------------------------

    def show_loading(self, text: str = "") -> None:
        """Show the overlay and start the spinner animation."""
        self._text = text
        self._angle = 0.0
        self.raise_()
        self.resize(self.parent().size())
        self.setVisible(True)
        self._timer.start(self._INTERVAL_MS)

    def hide_loading(self) -> None:
        """Hide the overlay and stop the animation timer."""
        self._timer.stop()
        self.setVisible(False)

    def set_text(self, text: str) -> None:
        """Update the status text while the overlay is showing."""
        self._text = text
        self.update()

    # -- internals -----------------------------------------------------------

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Semi-transparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        cx = self.width() / 2
        cy = self.height() / 2

        # Spinning arc
        r = self._SPINNER_RADIUS
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        pen = QPen(self._ACCENT, self._ARC_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        start = int(self._angle * 16)
        span = 270 * 16  # 3/4 arc
        painter.drawArc(rect, start, span)

        # Status text
        if self._text:
            painter.setPen(QColor(255, 255, 255, 220))
            font = QFont()
            font.setPointSize(11)
            painter.setFont(font)
            text_rect = QRectF(0, cy + r + 16, self.width(), 30)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._text)

        painter.end()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        """Resize overlay when parent resizes."""
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.resize(event.size())
        return super().eventFilter(obj, event)
