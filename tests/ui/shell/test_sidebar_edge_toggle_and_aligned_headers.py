"""Unit tests for unified header heights/colors and mid-sidebar paper-cut collapse toggle."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from cbpos.ui.views.management_view import ManagementView
from cbpos.ui.views.settings_view import SettingsView
from cbpos.ui.widgets.collapsible_sidebar import (
    CHEVRON_COLLAPSED,
    CHEVRON_EXPANDED,
    CollapsibleSidebar,
)
from tests.helpers.qss import rendered_qss

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    import cbpos.ui.widgets.collapsible_sidebar as module

    store = _FakeConfigStore({"sidebar_collapsed": False})
    monkeypatch.setattr(module.ConfigService, "get", store.get)
    monkeypatch.setattr(module.ConfigService, "set", store.set)
    return store


class TestHeaderHeightAndColorAlignment:
    def test_sidebar_header_and_management_header_have_identical_56px_height(self, db_session, config_store):
        sidebar = CollapsibleSidebar()
        management = ManagementView()
        settings = SettingsView()

        # Both headers must be exactly 56px fixed height
        assert hasattr(sidebar, "sidebar_header")
        assert sidebar.sidebar_header.objectName() == "SidebarHeader"
        assert sidebar.sidebar_header.maximumHeight() == 56
        assert sidebar.sidebar_header.minimumHeight() == 56

        assert management.management_header.maximumHeight() == 56
        assert management.management_header.minimumHeight() == 56

        assert settings.settings_header.maximumHeight() == 56
        assert settings.settings_header.minimumHeight() == 56

        # Vertical margins must be 0 to align bottoms
        assert sidebar._header_layout.contentsMargins().top() == 0
        assert sidebar._header_layout.contentsMargins().bottom() == 0

        assert management.management_header.layout().contentsMargins().top() == 0
        assert management.management_header.layout().contentsMargins().bottom() == 0

        assert settings.settings_header.layout().contentsMargins().top() == 0
        assert settings.settings_header.layout().contentsMargins().bottom() == 0

        sidebar.close()
        management.close()
        settings.close()


class TestMidSidebarEdgeToggleTab:
    def test_hamburger_toggle_removed_from_header_and_edge_toggle_attached(self, db_session, config_store):
        sidebar = CollapsibleSidebar()

        # Edge toggle button must exist
        assert hasattr(sidebar, "edge_toggle_btn")
        assert isinstance(sidebar.edge_toggle_btn, QPushButton)
        assert sidebar.edge_toggle_btn.objectName() == "SidebarEdgeToggle"
        assert sidebar.edge_toggle_btn.width() == 16
        assert sidebar.edge_toggle_btn.height() == 56
        assert sidebar.edge_toggle_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

        # Header layout must NOT contain the hamburger button
        for i in range(sidebar._header_layout.count()):
            widget = sidebar._header_layout.itemAt(i).widget()
            if widget is not None:
                assert widget.objectName() != "SidebarToggle"

        sidebar.close()

    def test_edge_toggle_repositions_flush_right_mid_edge_on_resize(self, db_session, config_store):
        sidebar = CollapsibleSidebar()
        sidebar.show()
        sidebar.resize(250, 800)

        btn_w = sidebar.edge_toggle_btn.width()
        btn_h = sidebar.edge_toggle_btn.height()

        assert sidebar.edge_toggle_btn.x() == 250 - btn_w
        assert sidebar.edge_toggle_btn.y() == (800 - btn_h) // 2

        sidebar.close()

    def test_toggle_switches_chevron_and_collapsed_logo(self, db_session, config_store):
        sidebar = CollapsibleSidebar()
        sidebar.finalize()
        sidebar.show()

        # Initially expanded
        assert sidebar.edge_toggle_btn.text() == CHEVRON_EXPANDED
        assert sidebar.lbl_logo.isVisible() is True
        assert sidebar.sidebar_header.height() == 56

        # Collapse
        sidebar.set_collapsed(True)
        assert sidebar.is_collapsed is True
        assert sidebar.edge_toggle_btn.text() == CHEVRON_COLLAPSED
        assert sidebar.lbl_logo.isVisible() is True
        assert sidebar.sidebar_header.height() == 56

        # Expand
        sidebar.set_collapsed(False)
        assert sidebar.is_collapsed is False
        assert sidebar.edge_toggle_btn.text() == CHEVRON_EXPANDED
        assert sidebar.lbl_logo.isVisible() is True
        assert sidebar.sidebar_header.height() == 56

        sidebar.close()


class TestHeaderAndToggleStylesheetRules:
    def test_qss_contains_unified_colors_and_paper_cut_edge_toggle(self):

        dark_css = rendered_qss("dark.qss")
        light_css = rendered_qss("light.qss")

        for css in (dark_css, light_css):
            assert "SidebarHeader" in css
            assert "SidebarEdgeToggle" in css
            assert "border-top-left-radius" in css

        # Dark mode color tokens
        assert "#252526" in dark_css  # SURFACE_1 (D20: #242428 snapped)
        assert "#2D2D30" in dark_css  # SURFACE_2 (D20: #2E2E34 snapped)
