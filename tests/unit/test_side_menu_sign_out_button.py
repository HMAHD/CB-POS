"""
#607: Sign Out was a flat 28px text button with a separate red icon QLabel
beside it -- the icon had a hand cursor but no click handler, so tapping
it did nothing. Now the icon sits on the button itself, which is at least
40px high, and name/role get 4px of breathing room.
"""

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QLabel

from cbpos.ui.widgets.side_menu import SideMenu

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def menu(qapp):
    widget = SideMenu()
    widget.resize(widget.width(), 900)
    widget.setVisible(True)
    yield widget
    widget.close()
    widget.deleteLater()


def test_sign_out_has_its_icon_on_the_button(menu: SideMenu) -> None:
    assert not menu.btn_logout.icon().isNull()
    assert not hasattr(menu, "btn_logout_icon")


def test_no_separate_dead_icon_label_next_to_sign_out(menu: SideMenu) -> None:
    row = menu.btn_logout.parentWidget()
    pointer_labels = [
        lbl for lbl in row.findChildren(QLabel) if lbl.cursor().shape() == Qt.CursorShape.PointingHandCursor
    ]
    assert pointer_labels == []


def test_sign_out_is_at_least_40px_high(menu: SideMenu) -> None:
    assert menu.btn_logout.height() >= 40
    assert menu.btn_logout.minimumHeight() >= 40


def test_clicking_the_icon_side_of_sign_out_logs_out(qtbot, menu: SideMenu) -> None:
    with qtbot.waitSignal(menu.logout_clicked, timeout=1000):
        # Left edge of the button is where the icon is drawn.
        qtbot.mouseClick(menu.btn_logout, Qt.MouseButton.LeftButton, pos=QPoint(14, menu.btn_logout.height() // 2))


def _layout_holding(layout, widget):
    if layout.indexOf(widget) >= 0:
        return layout
    for i in range(layout.count()):
        child = layout.itemAt(i).layout()
        if child is not None:
            found = _layout_holding(child, widget)
            if found is not None:
                return found
    return None


def test_name_and_role_have_4px_spacing(menu: SideMenu) -> None:
    info = _layout_holding(menu.lbl_username.parentWidget().layout(), menu.lbl_username)
    assert info.indexOf(menu.lbl_role) >= 0
    assert info.spacing() == 4
