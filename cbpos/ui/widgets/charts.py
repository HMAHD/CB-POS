"""
Custom QPainter-based chart widgets with smooth animations.

Provides VerticalBarChart, DonutChart, and HorizontalBarChart
for the CB POS dashboard. All rendering via QPainter — no
external charting dependencies required.
"""

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

# 12 distinct month colors (vibrant, readable on both themes)
MONTH_COLORS: list[str] = [
    "#FF6B6B",
    "#4ECDC4",
    "#45B7D1",
    "#96CEB4",
    "#FECA57",
    "#FF9FF3",
    "#54A0FF",
    "#5F27CD",
    "#01A3A4",
    "#F368E0",
    "#FF9F43",
    "#10AC84",
]

# Category / segment colors for donut chart
SEGMENT_COLORS: list[str] = [
    "#00BCEB",
    "#FF6B6B",
    "#FECA57",
    "#10AC84",
    "#5F27CD",
    "#FF9F43",
    "#45B7D1",
    "#F368E0",
]

# Hourly sales use theme accent gradient
HOURLY_COLORS: list[str] = [
    "#00BCEB",
    "#0CCCE8",
    "#19DCE5",
    "#26ECE2",
    "#33FCDF",
    "#00BCEB",
    "#0CCCE8",
    "#19DCE5",
    "#26ECE2",
    "#33FCDF",
    "#00BCEB",
    "#0CCCE8",
    "#19DCE5",
    "#26ECE2",
    "#33FCDF",
    "#00BCEB",
    "#0CCCE8",
]


def _get_text_color() -> QColor:
    """Get text color appropriate for current theme."""
    from cbpos.core.services.theme_service import ThemeService

    return QColor(ThemeService.get_icon_color())


def _get_grid_color() -> QColor:
    """Get subtle grid line color for current theme."""
    c = _get_text_color()
    c.setAlpha(25)
    return c


def _format_abbrev(val: float) -> str:
    """Abbreviate large numbers: 1500 → '1.5K', 1200000 → '1.2M'."""
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    elif val >= 1_000:
        return f"{val / 1_000:.1f}K"
    return f"{val:.0f}"


# ---------------------------------------------------------------------------
# Vertical Bar Chart
# ---------------------------------------------------------------------------
class VerticalBarChart(QWidget):
    """Animated vertical bar chart with per-bar colors.

    Data format: list of dicts with keys 'label', 'value', and optional 'color'.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._progress: float = 0.0
        self._anim = QPropertyAnimation(self, b"animProgress")
        self._anim.setDuration(800)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumHeight(180)

    # --- Animated property ---
    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, val: float) -> None:
        self._progress = val
        self.update()

    animProgress = pyqtProperty(float, _get_progress, _set_progress)

    def set_data(self, data: list[dict]) -> None:
        """Set chart data and trigger grow animation."""
        self._data = [
            {
                "label": d.get("label", ""),
                "value": float(d.get("value", 0)),
                "color": d.get("color"),
            }
            for d in data
        ]
        self._anim.stop()
        self._progress = 0.0
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, event) -> None:
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        text_color = _get_text_color()
        grid_color = _get_grid_color()

        left_m = 55
        right_m = 15
        top_m = 15
        bottom_m = 35

        chart_w = w - left_m - right_m
        chart_h = h - top_m - bottom_m
        if chart_w <= 0 or chart_h <= 0:
            painter.end()
            return

        max_val = max((d["value"] for d in self._data), default=1) or 1
        n = len(self._data)
        bar_spacing = chart_w / n
        bar_w = max(bar_spacing * 0.55, 4)

        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        # Y-axis grid + labels
        for i in range(5):
            y = top_m + chart_h - (chart_h * i / 4)
            val = max_val * i / 4
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRectF(0, y - 10, left_m - 8, 20),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                _format_abbrev(val),
            )
            painter.setPen(QPen(grid_color, 1))
            painter.drawLine(int(left_m), int(y), int(w - right_m), int(y))

        # Bars
        for i, d in enumerate(self._data):
            x = left_m + i * bar_spacing + (bar_spacing - bar_w) / 2
            bar_h = (d["value"] / max_val) * chart_h * self._progress
            y = top_m + chart_h - bar_h

            color = QColor(d["color"]) if d["color"] else QColor(MONTH_COLORS[i % 12])

            # Rounded-top bar
            radius = min(bar_w / 3, 4)
            path = QPainterPath()
            path.moveTo(x, top_m + chart_h)
            path.lineTo(x, y + radius)
            path.quadTo(x, y, x + radius, y)
            path.lineTo(x + bar_w - radius, y)
            path.quadTo(x + bar_w, y, x + bar_w, y + radius)
            path.lineTo(x + bar_w, top_m + chart_h)
            path.closeSubpath()

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)

            # Value label on top (only after animation mostly done)
            if bar_h > 22 and self._progress > 0.85:
                font.setPointSize(7)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QPen(QColor("#FFFFFF")))
                painter.drawText(
                    QRectF(x - 10, y - 16, bar_w + 20, 14),
                    int(Qt.AlignmentFlag.AlignCenter),
                    _format_abbrev(d["value"]),
                )
                font.setBold(False)
                painter.setFont(font)

            # X-axis label
            painter.setPen(QPen(text_color))
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(
                QRectF(
                    x - bar_spacing / 4,
                    top_m + chart_h + 5,
                    bar_spacing,
                    bottom_m - 5,
                ),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                d["label"],
            )

        painter.end()


# ---------------------------------------------------------------------------
# Donut Chart
# ---------------------------------------------------------------------------
class DonutChart(QWidget):
    """Animated donut (ring) chart with legend.

    Data format: list of dicts with 'label', 'value', and optional 'color'.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._progress: float = 0.0
        self._anim = QPropertyAnimation(self, b"animProgress")
        self._anim.setDuration(900)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumHeight(180)

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, val: float) -> None:
        self._progress = val
        self.update()

    animProgress = pyqtProperty(float, _get_progress, _set_progress)

    def set_data(self, data: list[dict]) -> None:
        self._data = [
            {
                "label": d.get("label", ""),
                "value": float(d.get("value", 0)),
                "color": d.get("color", SEGMENT_COLORS[i % len(SEGMENT_COLORS)]),
            }
            for i, d in enumerate(data)
        ]
        self._anim.stop()
        self._progress = 0.0
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, event) -> None:
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        text_color = _get_text_color()

        # Donut area on the left half, legend on the right
        donut_size = min(w * 0.5, h - 20)
        cx = donut_size / 2 + 10
        cy = h / 2
        outer_r = donut_size / 2 - 5
        inner_r = outer_r * 0.6

        total = sum(d["value"] for d in self._data)
        if total <= 0:
            painter.setPen(QPen(text_color))
            painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "No data")
            painter.end()
            return

        # Draw donut segments (sweep animation)
        start_angle = 90.0  # Start from 12 o'clock
        for d in self._data:
            span = (d["value"] / total) * 360.0 * self._progress
            color = QColor(d["color"])

            outer_rect = QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2)
            inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)

            path = QPainterPath()
            path.arcMoveTo(outer_rect, start_angle)
            path.arcTo(outer_rect, start_angle, span)
            path.arcTo(inner_rect, start_angle + span, -span)
            path.closeSubpath()

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)

            start_angle += span

        # Center total text
        if self._progress > 0.5:
            font = QFont()
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRectF(cx - outer_r, cy - 12, outer_r * 2, 24),
                int(Qt.AlignmentFlag.AlignCenter),
                _format_abbrev(total),
            )

        # Legend (right side)
        legend_x = donut_size + 20
        legend_y = max(15, (h - len(self._data) * 24) / 2)
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)

        for d in self._data:
            if legend_x + 50 > w:
                break
            color = QColor(d["color"])
            # Color swatch
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(legend_x, legend_y + 2, 12, 12), 2, 2)

            # Label + value
            pct = (d["value"] / total) * 100 if total > 0 else 0
            label_text = f"{d['label']}  ({pct:.0f}%)"
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRectF(legend_x + 18, legend_y, w - legend_x - 25, 18),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                label_text,
            )
            legend_y += 24

        painter.end()


# ---------------------------------------------------------------------------
# Horizontal Bar Chart
# ---------------------------------------------------------------------------
class HorizontalBarChart(QWidget):
    """Animated horizontal bar chart with labels and values.

    Data format: list of dicts with 'label' and 'value'.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._progress: float = 0.0
        self._bar_color: str = "#00BCEB"
        self._anim = QPropertyAnimation(self, b"animProgress")
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumHeight(150)

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, val: float) -> None:
        self._progress = val
        self.update()

    animProgress = pyqtProperty(float, _get_progress, _set_progress)

    def set_data(self, data: list[dict]) -> None:
        self._data = [
            {
                "label": d.get("label", ""),
                "value": float(d.get("value", 0)),
            }
            for d in data
        ]
        self._anim.stop()
        self._progress = 0.0
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, event) -> None:
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        text_color = _get_text_color()

        n = len(self._data)
        if n == 0:
            painter.end()
            return

        label_w = min(w * 0.28, 130)
        value_w = 70
        bar_area_w = w - label_w - value_w - 20
        bar_h = max(min((h - 10) / n - 8, 28), 12)
        total_row_h = bar_h + 8

        max_val = max((d["value"] for d in self._data), default=1) or 1

        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)

        y = max(5, (h - n * total_row_h) / 2)

        for d in self._data:
            # Label
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRectF(5, y, label_w - 5, bar_h),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                d["label"],
            )

            # Bar
            bw = (d["value"] / max_val) * bar_area_w * self._progress
            bar_rect = QRectF(label_w, y + 1, bw, bar_h - 2)
            bar_color = QColor(self._bar_color)

            path = QPainterPath()
            path.addRoundedRect(bar_rect, 3, 3)
            painter.setBrush(QBrush(bar_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)

            # Value text
            if self._progress > 0.6:
                painter.setPen(QPen(text_color))
                painter.drawText(
                    QRectF(label_w + bar_area_w + 5, y, value_w, bar_h),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    _format_abbrev(d["value"]),
                )

            y += total_row_h

        painter.end()
