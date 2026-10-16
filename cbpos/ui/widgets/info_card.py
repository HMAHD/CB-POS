from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from cbpos.ui.resources.icons import Icons


class InfoCard(QFrame):
    """Clean, flat KPI stat card for reports and dashboards.

    Displays an icon, small uppercase category title, and prominent value.
    Flat design with no QGraphicsDropShadowEffect to maintain snappy paint
    performance and prevent side-menu lag (#524, #543).
    """

    def __init__(
        self,
        title: str,
        value: str,
        icon_name: str,
        color: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("InfoCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(150, 64)
        self.setMaximumHeight(80)

        self._icon_name = icon_name
        self._color = color or "#00BCEB"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setObjectName("InfoCardIcon")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setFixedWidth(36)
        self._update_icon()
        layout.addWidget(self.icon_lbl)

        # Text Container (Title + Value)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setObjectName("InfoCardTitle")
        text_layout.addWidget(self.title_lbl)

        self.val_lbl = QLabel(value)
        self.val_lbl.setObjectName("InfoCardValue")
        text_layout.addWidget(self.val_lbl)

        layout.addLayout(text_layout, 1)

    def _update_icon(self) -> None:
        """Render the icon pixmap using current icon name and color."""
        pix = Icons.get(self._icon_name, self._color).pixmap(28, 28)
        self.icon_lbl.setPixmap(pix)

    def set_value(self, value: str) -> None:
        """Update the displayed metric value."""
        self.val_lbl.setText(str(value))

    def set_title(self, title: str) -> None:
        """Update the card title caption (upper-cased)."""
        self.title_lbl.setText(str(title).upper())

    def set_icon(self, icon_name: str, color: str | None = None) -> None:
        """Update the icon and accent color."""
        self._icon_name = icon_name
        if color:
            self._color = color
        self._update_icon()
