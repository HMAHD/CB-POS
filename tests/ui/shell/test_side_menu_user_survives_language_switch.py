"""
#580: SideMenu.retranslate_ui() reset the profile labels to "Guest" /
"No role", so any language switch during a shift wiped the logged-in
cashier's name and role from the menu until the next login. Logout also
never told the side menu, so the old user stayed shown after sign-out.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cbpos.core.utils.display_labels import display_role_name
from cbpos.i18n import _t, get_language, set_language
from cbpos.ui.main_window import MainWindow
from cbpos.ui.widgets.side_menu import SideMenu

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def menu(qapp):
    original_lang = get_language()
    widget = SideMenu()
    yield widget
    set_language(original_lang)
    widget.deleteLater()


def _cashier() -> SimpleNamespace:
    return SimpleNamespace(id=7, username="nimal", role=SimpleNamespace(name="Cashier"))


def test_user_survives_language_switches(menu: SideMenu) -> None:
    menu.set_user(_cashier())

    for lang in ("si", "ta", "en"):
        set_language(lang)
        assert menu.lbl_username.text() == "nimal"
        assert menu.lbl_role.text() == display_role_name("Cashier")  # translated built-in role (#583)


def test_logout_resets_side_menu_to_guest(menu: SideMenu) -> None:
    menu.set_user(_cashier())
    window = SimpleNamespace(
        user=_cashier(),
        watchdog=MagicMock(),
        stack=MagicMock(),
        login_view=object(),
        sales_view=SimpleNamespace(side_menu=menu),
    )

    MainWindow.logout(window)

    assert menu.lbl_username.text() == _t("side_menu.guest")
    set_language("si")
    assert menu.lbl_username.text() == _t("side_menu.guest")
