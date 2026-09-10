from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter
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
    Supports dynamic icon color updates when theme changes.
    """

    # Once any stylesheet applies to a QToolButton, Qt's CSS-based style
    # engine takes over its internal layout and does not reliably insert
    # real icon-to-text spacing on its own (#314) -- padding the icon
    # pixmap itself with transparent margin makes the gap real regardless
    # of style-engine quirks, without touching the QToolButtonIconOnly/
    # ToolButtonTextBesideIcon collapse-mode switching this button relies on.
    _ICON_SIZE = 24
    _ICON_TEXT_GAP = 12

    def __init__(self, text: str, icon_name: str):
        super().__init__()
        self.setText(text)
        self.icon_name = icon_name  # Store for theme updates

        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(50)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("SidebarButton")

        # Set initial icon with theme-appropriate color
        self.update_icon()

    def update_icon(self):
        """Update icon color (and icon-only vs beside-text padding) based
        on current theme and collapse state."""
        from cbpos.core.services.theme_service import ThemeService

        icon_color = ThemeService.get_icon_color()
        base_pixmap = Icons.get(self.icon_name, icon_color).pixmap(self._ICON_SIZE, self._ICON_SIZE)

        if self.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly:
            # Collapsed rail: icon-only, centered -- no trailing text to
            # make room for, so no padding.
            self.setIconSize(QSize(self._ICON_SIZE, self._ICON_SIZE))
            self.setIcon(QIcon(base_pixmap))
            return

        padded = QPixmap(self._ICON_SIZE + self._ICON_TEXT_GAP, self._ICON_SIZE)
        padded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(padded)
        painter.drawPixmap(0, 0, base_pixmap)
        painter.end()
        self.setIconSize(QSize(self._ICON_SIZE + self._ICON_TEXT_GAP, self._ICON_SIZE))
        self.setIcon(QIcon(padded))

    def set_active(self, active: bool):
        """Set the active state of the button and update styling."""
        self.setChecked(active)
