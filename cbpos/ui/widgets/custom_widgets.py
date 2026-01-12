from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton
from PyQt6.QtCore import Qt, QSize
from cbpos.ui.resources.icons import Icons


class InfoCard(QWidget):
    """
    Dashboard Info Card.
    Displays an Icon, a Value (Big), and a Label (Small).
    """

    def __init__(self, title: str, value: str, icon_name: str, color: str = "#00BCEB"):
        super().__init__()
        self.setFixedSize(220, 120)
        self.setObjectName("InfoCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # Icon
        icon_lbl = QLabel()
        icon_lbl.setPixmap(Icons.get(icon_name, color).pixmap(40, 40))
        icon_lbl.setFixedWidth(50)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # Text Container
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)

        self.val_lbl = QLabel(value)
        style = "font-size: 28px; font-weight: bold; color: {}; ".format(color)
        self.val_lbl.setStyleSheet(style)
        self.val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setObjectName("InfoCardTitle")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        text_layout.addWidget(self.val_lbl)
        text_layout.addWidget(self.title_lbl)
        text_layout.addStretch()

        layout.addWidget(icon_lbl)
        layout.addLayout(text_layout)

    def set_value(self, value: str):
        self.val_lbl.setText(value)


class SidebarButton(QToolButton):
    """
    Flat button for the sidebar with icon and text.
    """

    def __init__(self, text: str, icon_name: str):
        super().__init__()
        self.setText(text)
        from cbpos.core.services.theme_service import ThemeService

        icon_color = ThemeService.get_icon_color()
        # Use a slightly lighter color for inactive state if needed, or just use the theme color
        # For sidebar, inactive is usually grey, active is cyan.
        # But let's stick to the plan: use get_icon_color or hardcoded grey for inactive?
        # The original code used #AAAAAA (light grey).
        # In Light mode, #AAAAAA is visible on white.
        # So we might not strictly need to change this for INACTIVE state.
        # But let's ensure it's robust.
        self.setIcon(Icons.get(icon_name, icon_color))
        self.setIconSize(QSize(24, 24))
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(50)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("SidebarButton")

    def set_active(self, active: bool):
        """Set the active state of the button and update styling."""
        self.setChecked(active)
