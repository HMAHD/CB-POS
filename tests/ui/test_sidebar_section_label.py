"""
#315: all 10 of ManagementView's nav items sat in one flat,
undifferentiated vertical list with equal visual weight. add_section_label()
gives the sidebar a way to insert a resting point between groups (e.g.
day-to-day operational screens vs. management/admin ones) -- a divider
line that stays visible even when collapsed, with a small-caps label
above it that hides once there's no room for text on the icon-only rail.
"""

import pytest
from PyQt6.QtWidgets import QFrame, QLabel

from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    """In-memory stand-in for ConfigService so these tests never touch
    the real, developer-shared settings.json on disk."""

    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    import cbpos.ui.widgets.collapsible_sidebar as collapsible_sidebar_module

    store = _FakeConfigStore({"sidebar_collapsed": False})
    monkeypatch.setattr(collapsible_sidebar_module.ConfigService, "get", store.get)
    monkeypatch.setattr(collapsible_sidebar_module.ConfigService, "set", store.set)
    return store


class TestAddSectionLabel:
    def test_returns_a_label_with_the_upper_cased_text(self, config_store):
        sidebar = CollapsibleSidebar()
        label = sidebar.add_section_label("Management")

        assert isinstance(label, QLabel)
        assert label.text() == "MANAGEMENT"
        assert label.objectName() == "SidebarSectionLabel"

    def test_the_label_is_tracked_for_collapse_visibility_toggling(self, config_store):
        sidebar = CollapsibleSidebar()
        label = sidebar.add_section_label("Management")

        assert label in sidebar._section_labels

    def test_a_divider_frame_is_inserted_alongside_the_label(self, config_store):
        sidebar = CollapsibleSidebar()
        sidebar.add_section_label("Management")

        dividers = sidebar.findChildren(QFrame, "SidebarSectionDivider")
        assert len(dividers) == 1


class TestSectionLabelCollapseBehavior:
    def test_label_text_hides_when_the_sidebar_collapses(self, config_store):
        sidebar = CollapsibleSidebar()
        label = sidebar.add_section_label("Management")
        sidebar.finalize()
        sidebar.show()

        sidebar.set_collapsed(True)

        assert label.isVisible() is False

    def test_label_text_reappears_when_expanded_again(self, config_store):
        sidebar = CollapsibleSidebar()
        label = sidebar.add_section_label("Management")
        sidebar.finalize()
        sidebar.show()

        sidebar.set_collapsed(True)
        sidebar.set_collapsed(False)

        assert label.isVisible() is True

    def test_divider_stays_visible_when_collapsed(self, config_store):
        """The divider line is the part that still needs to signal a
        group break even on the icon-only rail -- only the label text
        (which has no room to render there) should hide."""
        sidebar = CollapsibleSidebar()
        sidebar.add_section_label("Management")
        sidebar.finalize()
        sidebar.show()

        sidebar.set_collapsed(True)

        divider = sidebar.findChildren(QFrame, "SidebarSectionDivider")[0]
        assert divider.isVisible() is True

    def test_starting_collapsed_hides_the_label_from_the_start(self, config_store):
        config_store.set("sidebar_collapsed", True)
        sidebar = CollapsibleSidebar()
        label = sidebar.add_section_label("Management")
        sidebar.finalize()
        sidebar.show()

        assert label.isVisible() is False
