"""Shared, compact top-of-screen title strip: icon + screen name.

A third of ManagementView's screens (Users, Stock Take, Purchasing)
showed nothing identifying which screen was open beyond the sidebar's
own highlighted nav button; others used one of three different ad-hoc
title conventions. This widget standardizes "where am I" across all of
them without touching whatever secondary navigation (tabs, a sidebar,
or none) each screen already uses for its own content (#316).
"""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.resources.icons import Icons


class PageHeader(QWidget):
    """Compact icon + title strip, placed at the very top of a screen."""

    def __init__(self, icon_name: str = "", title: str = "", parent=None) -> None:
        """Build the icon+title row and register for theme-driven icon refresh.

        Args:
            icon_name: Initial ``Icons.*`` FontAwesome icon name.
            title: Initial screen-name text.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("PageHeader")
        self._icon_name = icon_name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("PageHeaderIcon")
        layout.addWidget(self._icon_label)

        self._title_label = QLabel()
        self._title_label.setObjectName("PageHeaderTitle")
        layout.addWidget(self._title_label)
        layout.addStretch(1)

        if icon_name:
            self.set_icon(icon_name)
        if title:
            self.set_title(title)

        ThemeService.register_theme_callback(self._on_theme_changed)

    def set_icon(self, icon_name: str) -> None:
        """Set the header's icon (an ``Icons.*`` FontAwesome name)."""
        self._icon_name = icon_name
        self._refresh_icon()

    def set_title(self, title: str) -> None:
        """Set the header's screen-name text."""
        self._title_label.setText(title)

    def _refresh_icon(self) -> None:
        if not self._icon_name:
            return
        icon = Icons.get(self._icon_name, ThemeService.get_icon_color())
        self._icon_label.setPixmap(icon.pixmap(18, 18))

    def _on_theme_changed(self) -> None:
        self._refresh_icon()
