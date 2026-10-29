"""
#591: CollapsibleSidebar (Settings and Management) stacked its nav buttons
and the POS/Logout pair in one layout with no scroll area, so at 1366x768
POS (then Logout) was clipped. The nav list now scrolls, POS/Logout are
pinned outside it, and below ~800px the buttons go compact.
"""

import pytest
from PyQt6.QtWidgets import QApplication, QScrollArea

from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

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


def _build(collapsed: bool = False) -> CollapsibleSidebar:
    sidebar = CollapsibleSidebar()
    for i in range(4):
        sidebar.add_nav_button(f"Item {i}", "fa5s.store", i)
    sidebar.add_section_label("Management")
    for i in range(4, 11):
        sidebar.add_nav_button(f"Item {i}", "fa5s.store", i)
    sidebar.finalize()
    if collapsed:
        sidebar.set_collapsed(True)
        sidebar._anim_min.stop()
        sidebar._anim_max.stop()
        sidebar.setFixedWidth(70)
    return sidebar


@pytest.fixture
def sidebars():
    made = []
    yield made
    for s in made:
        s.close()
        s.deleteLater()


def _show_at_height(sidebar: CollapsibleSidebar, height: int) -> None:
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QResizeEvent

    sidebar.resize(sidebar.width(), height)
    sidebar.show()
    QApplication.processEvents()
    if sidebar.height() != height:
        sidebar.resizeEvent(QResizeEvent(QSize(sidebar.width(), height), sidebar.size()))


def _fully_inside(parent, child) -> bool:
    top_left = child.mapTo(parent, child.rect().topLeft())
    bottom_right = child.mapTo(parent, child.rect().bottomRight())
    return parent.rect().contains(top_left) and parent.rect().contains(bottom_right)


def test_pos_and_logout_removed_from_sidebar(config_store, sidebars):
    """POS and Logout buttons were moved to the persistent top headers, freeing sidebar space."""
    sidebar = _build()
    sidebars.append(sidebar)
    assert not hasattr(sidebar, "btn_pos")
    assert not hasattr(sidebar, "btn_logout")
    assert not hasattr(sidebar, "_bottom_widget")


@pytest.mark.parametrize("collapsed", [False, True])
def test_every_nav_button_is_reachable_by_scrolling(config_store, sidebars, collapsed):
    sidebar = _build(collapsed)
    sidebars.append(sidebar)
    _show_at_height(sidebar, 450)

    scroll = sidebar.nav_scroll
    assert isinstance(scroll, QScrollArea)
    assert scroll.verticalScrollBar().maximum() > 0
    for btn in sidebar.nav_buttons:
        assert scroll.widget().isAncestorOf(btn)
        scroll.ensureWidgetVisible(btn)
        QApplication.processEvents()
        assert _fully_inside(scroll.viewport(), btn)


def test_compact_mode_below_800px(config_store, sidebars):
    sidebar = _build()
    sidebars.append(sidebar)
    _show_at_height(sidebar, 728)

    assert sidebar.is_compact
    assert sidebar.nav_layout.spacing() == 4
    assert all(btn.height() == 40 for btn in sidebar.nav_buttons)


def test_tall_screens_keep_the_normal_buttons(config_store, sidebars):
    sidebar = _build()
    sidebars.append(sidebar)
    _show_at_height(sidebar, 728)
    _show_at_height(sidebar, 1040)

    assert not sidebar.is_compact
    assert all(btn.height() == 50 for btn in sidebar.nav_buttons)
    assert sidebar.nav_scroll.verticalScrollBar().maximum() == 0
