"""
#728: the side menu opened Management for ``admin.manage_roles`` while the Users tab inside was
gated on ``admin.manage_users``, and opened Settings for ``admin.tools`` while Admin Tools inside
was gated on ``admin.settings`` -- so those users landed on a screen without the tab they came for.
Whoever the menu lets in must see at least one tab they're allowed to use.
"""

from types import SimpleNamespace

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.ui.widgets.side_menu import SideMenu

pytestmark = pytest.mark.usefixtures("qapp")


def _only(code: str) -> SimpleNamespace:
    """A user whose custom role has exactly one permission."""
    role = SimpleNamespace(name="Custom", permissions=[SimpleNamespace(code=code)])
    return SimpleNamespace(id=1, username="someone", role=role)


@pytest.fixture
def menu(qapp):
    widget = SideMenu()
    yield widget
    widget.deleteLater()


@pytest.fixture
def management(qapp, db_session):
    from cbpos.ui.views.management_view import ManagementView

    view = ManagementView()
    yield view
    view.deleteLater()


def _shown(button) -> bool:
    return not button.isHidden()


def _visible_tabs(sidebar) -> list[int]:
    return [i for i, button in enumerate(sidebar.nav_buttons) if _shown(button)]


def _landing_tab(sidebar):
    """The sidebar button highlighted as the page on screen."""
    (active,) = [button for button in sidebar.nav_buttons if button.property("active")]
    return active


EVERY_PERMISSION = Permissions.get_all()


class TestManagement:
    def test_role_manager_opens_management_and_sees_users(self, menu, management):
        user = _only(Permissions.ADMIN_MANAGE_ROLES)
        menu.set_user(user)
        management.set_user(user)

        assert _shown(menu.btn_management)
        assert _shown(management.btn_users)

    @pytest.mark.parametrize("code", EVERY_PERMISSION)
    def test_menu_offers_management_exactly_when_a_tab_is_usable(self, menu, management, code):
        user = _only(code)
        menu.set_user(user)
        management.set_user(user)

        tabs = _visible_tabs(management.sidebar)
        assert _shown(menu.btn_management) == bool(tabs)
        if tabs:
            assert _shown(_landing_tab(management.sidebar))


@pytest.fixture
def settings(qapp, db_session):
    from cbpos.ui.views.settings_view import SettingsView

    view = SettingsView()
    yield view
    view.deleteLater()


class TestSettings:
    def test_admin_tools_user_opens_settings_and_sees_admin_tools(self, menu, settings):
        user = _only(Permissions.ADMIN_TOOLS)
        menu.set_user(user)
        settings.set_user(user)

        assert _shown(menu.btn_settings)
        assert _shown(settings.btn_admin_tools)

    @pytest.mark.parametrize("code", EVERY_PERMISSION)
    def test_menu_offers_settings_exactly_when_a_page_is_usable(self, menu, settings, code):
        user = _only(code)
        menu.set_user(user)
        settings.set_user(user)

        pages = _visible_tabs(settings.sidebar)
        assert _shown(menu.btn_settings) == bool(pages)
        if pages:
            assert _shown(_landing_tab(settings.sidebar))
