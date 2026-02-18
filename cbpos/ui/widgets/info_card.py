from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from cbpos.ui.resources.icons import Icons


class InfoCard(QFrame):
    def __init__(
        self,
        title,
        value,
        icon_name,
        trend_text=None,
        trend_positive=True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("InfoCard")  # For QSS styling
        self.setFixedSize(280, 140)  # Wider for better spacing

        # Store icon name for theme updates
        self.icon_name = icon_name
        self.icon_label = None

        # Shadow Effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(5)

        # Top Row: Icon + Title
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        # Icon
        self.icon_label = QLabel()
        self.icon_label.setObjectName("CardIcon")
        self.update_icon()
        top_layout.addWidget(self.icon_label)

        top_layout.addStretch()

        # Title
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        top_layout.addWidget(title_label)

        layout.addLayout(top_layout)

        layout.addSpacing(10)

        # Value (Center)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("CardValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value_label)

        layout.addSpacing(5)

        # Trend (Bottom)
        self.trend_text = trend_text
        self.trend_positive = trend_positive
        self.trend_label = QLabel(trend_text if trend_text else "")
        self.trend_label.setObjectName("CardTrend")
        self.trend_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Set property for CSS targeting
        if trend_text:
            self.trend_label.setProperty("trendType", "positive" if trend_positive else "negative")

        layout.addWidget(self.trend_label)

    def update_icon(self):
        """Update icon color based on current theme."""
        if self.icon_label is None:
            return
        from cbpos.core.services.theme_service import ThemeService
        # Use white icon with 40% opacity
        icon = Icons.get(self.icon_name, "white")
        self.icon_label.setPixmap(icon.pixmap(40, 40))

    def set_value(self, text: str):
        """Update the main value label."""
        self.value_label.setText(text)

    def set_trend(self, text: str, positive: bool = True):
        """Update the trend label and property."""
        self.trend_label.setText(text)
        self.trend_label.setProperty("trendType", "positive" if positive else "negative")
        # Force style refresh
        self.trend_label.style().unpolish(self.trend_label)
        self.trend_label.style().polish(self.trend_label)
