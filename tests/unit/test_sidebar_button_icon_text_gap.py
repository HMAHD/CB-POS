"""
Every sidebar nav row (Dashboard, Inventory, Purchasing, ...) showed its
icon touching the label text with no visible gap. SidebarButton is a
plain QToolButton in ToolButtonTextBesideIcon mode -- the only relevant
QSS rule (padding-left: 20px) is the gap between the button's left border
and the icon, not between the icon and the text that follows it. Once
any stylesheet applies to a QToolButton, Qt's style engine takes over
layout and doesn't reliably insert real icon-to-text spacing on its own.

Fixed by padding the icon pixmap itself with transparent margin on its
trailing edge -- a real, guaranteed gap regardless of style-engine
behavior -- while leaving the icon unpadded when the button is collapsed
to icon-only (no trailing text to make room for).
"""

import pytest
from PyQt6.QtCore import Qt

from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar
from cbpos.ui.widgets.custom_widgets import SidebarButton

pytestmark = pytest.mark.usefixtures("qapp")


class TestSidebarButtonIconTextGap:
    def test_icon_is_padded_wider_than_its_native_size_when_showing_text(self):
        btn = SidebarButton("Dashboard", "fa5s.home")
        assert btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        assert btn.iconSize().width() > btn._ICON_SIZE
        assert btn.iconSize().height() == btn._ICON_SIZE

    def test_icon_is_not_padded_when_collapsed_to_icon_only(self):
        btn = SidebarButton("Dashboard", "fa5s.home")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.update_icon()
        assert btn.iconSize().width() == btn._ICON_SIZE
        assert btn.iconSize().height() == btn._ICON_SIZE

    def test_switching_back_to_beside_text_restores_the_padded_icon(self):
        btn = SidebarButton("Dashboard", "fa5s.home")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.update_icon()
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.update_icon()
        assert btn.iconSize().width() > btn._ICON_SIZE


class TestSidebarCollapseKeepsIconPaddingInSync:
    """ConfigService persists "sidebar_collapsed" to real settings.json, so
    a fresh CollapsibleSidebar() can start in either state depending on
    what an earlier test (or a developer's own dev-machine settings) left
    behind. These tests force a known starting state via monkeypatch
    instead of relying on whatever ConfigService.get() happens to return."""

    def _make_sidebar(self, monkeypatch, start_collapsed: bool) -> CollapsibleSidebar:
        import cbpos.ui.widgets.collapsible_sidebar as collapsible_sidebar_module

        monkeypatch.setattr(
            collapsible_sidebar_module.ConfigService,
            "get",
            lambda key: start_collapsed if key == "sidebar_collapsed" else None,
        )
        monkeypatch.setattr(collapsible_sidebar_module.ConfigService, "set", lambda key, value: None)

        sidebar = CollapsibleSidebar()
        sidebar.add_nav_button("Dashboard", "fa5s.home", 0)
        sidebar.finalize()
        return sidebar

    def test_toggling_to_collapsed_removes_padding_from_nav_buttons(self, monkeypatch):
        sidebar = self._make_sidebar(monkeypatch, start_collapsed=False)

        sidebar.toggle()  # expanded -> collapsed

        assert sidebar.is_collapsed is True
        for btn in sidebar.nav_buttons:
            assert btn.iconSize().width() == btn._ICON_SIZE

    def test_toggling_back_to_expanded_restores_padding(self, monkeypatch):
        sidebar = self._make_sidebar(monkeypatch, start_collapsed=False)

        sidebar.toggle()  # expanded -> collapsed
        sidebar.toggle()  # collapsed -> expanded

        assert sidebar.is_collapsed is False
        for btn in sidebar.nav_buttons:
            assert btn.iconSize().width() > btn._ICON_SIZE


class TestNavButtonsHaveNoStringPaddingHack:
    def test_sidebar_has_no_bottom_exit_buttons_and_nav_buttons_have_no_padding_hack(self):
        sidebar = CollapsibleSidebar()
        sidebar.add_nav_button("Dashboard", "fa5s.tachometer-alt", 0)
        sidebar.finalize()

        assert not hasattr(sidebar, "btn_pos")
        assert not hasattr(sidebar, "btn_logout")
        for btn in sidebar.nav_buttons:
            assert not btn.text().startswith(" ")
