"""
#590: the POS side menu stacked its nav tiles, profile, Sign Out and the
Settings/Power toolbar in one layout with no scroll area. At 1366x768 the
whole thing needs ~1000px, so the bottom (profile, Sign Out, toolbar) was
clipped. The tiles now scroll; the bottom block is pinned outside the
scroll area; below ~800px the tiles go compact.
"""

import pytest
from PyQt6.QtWidgets import QApplication, QScrollArea

from cbpos.ui.widgets.side_menu import SideMenu

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def menu(qapp):
    widget = SideMenu()
    widget.setVisible(True)
    yield widget
    widget.close()
    widget.deleteLater()


def _show_at_height(menu: SideMenu, height: int) -> None:
    menu.resize(menu.width(), height)
    QApplication.processEvents()


def _fully_inside(menu: SideMenu, child) -> bool:
    top_left = child.mapTo(menu, child.rect().topLeft())
    bottom_right = child.mapTo(menu, child.rect().bottomRight())
    return menu.rect().contains(top_left) and menu.rect().contains(bottom_right)


@pytest.mark.parametrize("height", [600, 690, 728])
def test_profile_sign_out_and_toolbar_stay_visible_on_short_screens(menu: SideMenu, height: int) -> None:
    _show_at_height(menu, height)

    for child in (menu.lbl_username, menu.btn_logout, menu.btn_settings, menu.btn_fullscreen, menu.btn_power):
        assert child.isVisible()
        assert _fully_inside(menu, child), child.objectName()


def test_tiles_live_in_a_scroll_area_that_scrolls_when_short(menu: SideMenu) -> None:
    _show_at_height(menu, 500)

    scroll = menu.nav_scroll
    assert isinstance(scroll, QScrollArea)
    for tile in menu._nav_buttons:
        assert scroll.widget().isAncestorOf(tile)
    assert scroll.verticalScrollBar().maximum() > 0

    last = menu._nav_buttons[-1]
    scroll.ensureWidgetVisible(last)
    QApplication.processEvents()
    top = last.mapTo(scroll.viewport(), last.rect().topLeft())
    bottom = last.mapTo(scroll.viewport(), last.rect().bottomRight())
    assert scroll.viewport().rect().contains(top)
    assert scroll.viewport().rect().contains(bottom)


def test_compact_mode_below_800px(menu: SideMenu) -> None:
    _show_at_height(menu, 728)

    assert menu.is_compact
    assert menu.nav_layout.spacing() == 8
    assert all(tile.minimumHeight() == 60 for tile in menu._nav_buttons)


def test_tall_screens_keep_the_roomy_tiles(menu: SideMenu) -> None:
    _show_at_height(menu, 1040)

    assert not menu.is_compact
    assert menu.nav_layout.spacing() == 20
    assert all(tile.minimumHeight() == 80 for tile in menu._nav_buttons)
    assert menu.nav_scroll.verticalScrollBar().maximum() == 0


def test_going_back_to_a_tall_screen_restores_full_size(menu: SideMenu) -> None:
    _show_at_height(menu, 728)
    _show_at_height(menu, 1040)

    assert not menu.is_compact
    assert menu.nav_layout.spacing() == 20
