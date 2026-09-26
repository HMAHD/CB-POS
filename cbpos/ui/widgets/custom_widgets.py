from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from cbpos.ui.resources.icons import Icons


class InfoCard(QWidget):
    """
    Dashboard Info Card.
    Displays an Icon, a Value (Big), and a Label (Small).
    """

    def __init__(self, title: str, value: str, icon_name: str, color: str = "#00BCEB"):
        """Build the icon + value + title layout.

        Args:
            title: Small caption shown under the value (upper-cased for display).
            value: Big value text (e.g. a formatted count or currency amount).
            icon_name: qtawesome icon name.
            color: Accent color used for the icon and value text.
        """
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
        style = f"font-size: 28px; font-weight: bold; color: {color}; "
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
        """Update the displayed value text."""
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
        """Create a checkable, auto-exclusive sidebar button.

        Args:
            text: Button label.
            icon_name: qtawesome icon name; recolored on theme/active-state
                changes via ``update_icon()``.
        """
        super().__init__()
        self.setText(text)
        self.icon_name = icon_name  # Store for theme updates
        self._is_active = False

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
        on current theme, active state, and collapse state.

        The active/checked QSS rule recolors the button's background,
        border, and text -- but a qtawesome icon is a baked pixmap, not
        something QSS can recolor, so without this the icon glyph stayed
        the same secondary color regardless of active state. That made
        the collapsed (icon-only) sidebar rail show almost no visible
        difference for the current section, since there's no text left
        to carry the accent color either (#287).
        """
        from cbpos.core.services.theme_service import ThemeService

        icon_color = ThemeService.get_accent_color() if self._is_active else ThemeService.get_icon_color()
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
        self._is_active = active
        self.setChecked(active)
        self.update_icon()
