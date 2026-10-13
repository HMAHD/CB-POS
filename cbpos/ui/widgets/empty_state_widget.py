"""Shared "nothing here yet" visual: large muted icon + title + optional subtitle.

Every screen that needed an empty state built its own: Reports had a
custom-painted bar-chart icon widget, the POS cart was plain text in a
QLabel, and several others used their own variations again -- three (or
more) different implementations of the same idea, with no shared visual
language between them (#254). This widget standardizes the icon+title
version of that pattern; it works as a normal layout child (e.g. a
full-page placeholder) or as a widget manually positioned over a
table's viewport (e.g. the cart), same as any other QWidget.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.resources.icons import Icons


class EmptyStateWidget(QWidget):
    """Large muted icon, a title, and an optional subtitle, all centered."""

    def __init__(self, icon_name: str, parent=None) -> None:
        """Build the centered icon/title/subtitle layout.

        Args:
            icon_name: qtawesome icon name for the muted center icon.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("EmptyStateWidget")
        self._icon_name = icon_name

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("EmptyStateIcon")
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label)

        self._title_label = QLabel()
        self._title_label.setObjectName("EmptyStateTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_label)

        self._subtitle_label = QLabel()
        self._subtitle_label.setObjectName("EmptyStateSubtitle")
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setVisible(False)
        layout.addWidget(self._subtitle_label)

        self._refresh_icon()
        ThemeService.register_theme_callback(self._refresh_icon)

        if parent is not None:
            parent.installEventFilter(self)

    def eventFilter(self, watched, event):
        """Auto-resize overlay to match parent viewport size when parent resizes."""
        from PyQt6.QtCore import QEvent

        if watched is self.parent() and event.type() == QEvent.Type.Resize:
            self.resize(watched.size())
        return super().eventFilter(watched, event)

    def setVisible(self, visible: bool) -> None:
        """Show or hide widget, updating size from parent viewport on show."""
        super().setVisible(visible)
        if visible and self.parent() is not None:
            self.resize(self.parent().size())

    def set_title(self, text: str) -> None:
        """Set the bold headline text (e.g. "Cart is Empty")."""
        self._title_label.setText(text)

    def setText(self, text: str) -> None:
        """Compatibility with QLabel.setText."""
        self.set_title(text)

    def text(self) -> str:
        """Compatibility with QLabel.text."""
        return self._title_label.text()

    def set_subtitle(self, text: str) -> None:
        """Set optional smaller supporting text; hidden if *text* is empty."""
        self._subtitle_label.setText(text)
        self._subtitle_label.setVisible(bool(text))

    def _refresh_icon(self) -> None:
        # Matches the muted gray already used for empty-state text
        # (QLabel#EmptyCartLabel/EmptyTableLabel) in each theme -- a
        # qtawesome icon is a baked pixmap, so QSS can't recolor it the
        # way it recolors text; this keeps it in the same palette anyway.
        color = "#888888" if ThemeService.current_theme.lower() != "light" else "#6C757D"
        self._icon_label.setPixmap(Icons.get(self._icon_name, color).pixmap(64, 64))
