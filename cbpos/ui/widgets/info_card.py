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
        self, title, value, icon_name, trend_text=None, trend_positive=True, parent=None
    ):
        super().__init__(parent)
        self.setFixedSize(240, 140)
        self.setStyleSheet(
            """
            InfoCard {
                background-color: #003366;
                border-radius: 8px;
            }
        """
        )

        # Shadow Effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # Top Row: Icon + Title
        top_layout = QHBoxLayout()

        # Icon
        icon_label = QLabel()
        icon_label.setPixmap(
            Icons.get(icon_name, "rgba(255, 255, 255, 0.3)").pixmap(32, 32)
        )
        top_layout.addWidget(icon_label)

        top_layout.addStretch()

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #AAAAAA; font-size: 12px; font-weight: bold;")
        top_layout.addWidget(title_label)

        layout.addLayout(top_layout)

        # Value (Center)
        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        layout.addWidget(value_label)

        # Trend (Bottom)
        if trend_text:
            trend_label = QLabel(trend_text)
            trend_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            color = "#39FF14" if trend_positive else "#FF4136"
            trend_label.setStyleSheet("color: {}; font-size: 11px;".format(color))
            layout.addWidget(trend_label)
        else:
            layout.addStretch()
