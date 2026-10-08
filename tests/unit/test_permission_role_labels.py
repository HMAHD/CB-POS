"""
#583: permission rows showed the DB description generated from the code ("Sales Add_Item"),
groups / built-in role names / Activity Log event types were shown raw, so si and ta users
saw English everywhere. Labels are now looked up by code at display time (which also fixes
databases created before this), built-in roles are translated, custom roles show as typed.
"""

import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.utils.display_labels import (
    display_role_name,
    event_type_label,
    permission_group_label,
    permission_label,
)
from cbpos.i18n import get_language, set_language, translate_in

pytestmark = pytest.mark.usefixtures("qapp")

LATIN = re.compile(r"[A-Za-z]")
# Acronyms that stay as-is in every language
ALLOWED_LATIN = {"GRN"}


def _english_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z_]+", text) if w not in ALLOWED_LATIN]


@pytest.fixture
def lang():
    """Switch language for one test, restoring the original afterwards."""
    original = get_language()
    yield set_language
    set_language(original)


ALL_CODES = Permissions.get_all()
ALL_GROUPS = list(Permissions.get_groups())


class TestPermissionLabels:
    def test_old_style_db_description_is_replaced_by_the_label(self, lang):
        lang("en")
        # What seed.py / database_setup_service.py stored before #583
        old_description = "sales.add_item".replace(".", " ").title()
        assert old_description == "Sales Add_Item"

        assert permission_label("sales.add_item", old_description) == "Add items to a bill"

    def test_unknown_code_falls_back_to_the_stored_description(self):
        assert permission_label("plugin.thing", "Plugin Thing") == "Plugin Thing"
        assert permission_label("plugin.thing") == "plugin.thing"

    @pytest.mark.parametrize("code", ALL_CODES)
    def test_every_permission_has_an_english_label_without_underscores(self, code):
        label = translate_in("en", f"permission.code.{code}")
        assert label != f"permission.code.{code}"
        assert "_" not in label

    @pytest.mark.parametrize("language", ["si", "ta"])
    @pytest.mark.parametrize("code", ALL_CODES)
    def test_every_permission_is_translated(self, lang, language, code):
        lang(language)
        assert _english_words(permission_label(code, "Sales Add_Item")) == []

    @pytest.mark.parametrize("language", ["si", "ta"])
    @pytest.mark.parametrize("group", [*ALL_GROUPS, None])
    def test_every_group_is_translated(self, lang, language, group):
        lang(language)
        assert _english_words(permission_group_label(group)) == []


class TestRoleNames:
    @pytest.mark.parametrize("language", ["si", "ta"])
    @pytest.mark.parametrize("name", ["Admin", "Manager", "Cashier"])
    def test_built_in_roles_are_translated(self, lang, language, name):
        lang(language)
        label = display_role_name(SimpleNamespace(name=name))
        assert label and not LATIN.search(label)

    @pytest.mark.parametrize("language", ["en", "si", "ta"])
    def test_custom_role_shows_exactly_as_typed(self, lang, language):
        lang(language)
        assert display_role_name(SimpleNamespace(name="Supervisor")) == "Supervisor"
        assert display_role_name("night shift lead") == "night shift lead"

    def test_english_built_in_names_unchanged(self, lang):
        lang("en")
        assert [display_role_name(n) for n in ("Admin", "Manager", "Cashier")] == ["Admin", "Manager", "Cashier"]


class TestEventTypes:
    @pytest.mark.parametrize("language", ["si", "ta"])
    @pytest.mark.parametrize(
        "event_type", ["LOGIN", "LOGOUT", "TIMEOUT", "SECURITY", "INVENTORY", "TRANSACTION", "CREDIT", "PURCHASE"]
    )
    def test_event_types_are_translated(self, lang, language, event_type):
        lang(language)
        assert not LATIN.search(event_type_label(event_type))

    def test_unknown_event_type_shows_as_stored(self):
        assert event_type_label("SYNC") == "SYNC"


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

ROLE_ROWS = [SimpleNamespace(id=i, name=n, permissions=[]) for i, n in enumerate(["Admin", "Manager", "Supervisor"], 1)]


def _perm_rows() -> list[SimpleNamespace]:
    """Permission rows as an old database holds them: generated English descriptions."""
    rows = []
    for n, (group, codes) in enumerate(Permissions.get_groups().items()):
        for m, code in enumerate(codes):
            rows.append(
                SimpleNamespace(id=n * 100 + m, code=code, description=code.replace(".", " ").title(), group=group)
            )
    rows.append(SimpleNamespace(id=9999, code="sales.view", description="Sales View", group=None))
    return rows


@pytest.fixture
def permission_dialog(qtbot):
    from cbpos.ui.dialogs.permission_dialog import PermissionDialog

    def _open() -> PermissionDialog:
        with (
            patch("cbpos.ui.dialogs.permission_dialog.UserService.get_all_roles", return_value=ROLE_ROWS),
            patch(
                "cbpos.ui.dialogs.permission_dialog.PermissionService.get_all_permissions",
                return_value=_perm_rows(),
            ),
        ):
            dialog = PermissionDialog()
        qtbot.addWidget(dialog)
        return dialog

    return _open


def _tree_texts(dialog) -> list[str]:
    texts = []
    root = dialog.tree.invisibleRootItem()
    for g in range(root.childCount()):
        group = root.child(g)
        texts.append(group.text(0))
        texts.extend(group.child(p).text(0) for p in range(group.childCount()))
    return texts


class TestPermissionDialog:
    @pytest.mark.parametrize("language", ["si", "ta"])
    def test_no_english_permission_group_or_built_in_role_text(self, lang, permission_dialog, language):
        lang(language)
        dialog = permission_dialog()

        for text in _tree_texts(dialog):
            assert _english_words(text) == [], text
        header = dialog.tree.headerItem()
        headers = [header.text(i) for i in range(dialog.tree.columnCount())]
        assert not LATIN.search(" ".join(headers[:3]))
        assert headers[3] == "Supervisor"

    def test_old_database_rows_show_readable_english(self, lang, permission_dialog):
        lang("en")
        texts = _tree_texts(permission_dialog())
        assert "Add items to a bill" in texts
        assert "Sales Add_Item" not in texts
        assert "Other" in texts

    def test_cell_lock_and_delegate_still_in_place(self, lang, permission_dialog):
        from cbpos.ui.dialogs.permission_dialog import LOCKED_CELL_ROLE, _RoleCheckDelegate

        lang("si")
        dialog = permission_dialog()
        assert isinstance(dialog.tree.itemDelegateForColumn(1), _RoleCheckDelegate)
        locked = []
        root = dialog.tree.invisibleRootItem()
        for g in range(root.childCount()):
            group = root.child(g)
            for p in range(group.childCount()):
                if group.child(p).data(1, LOCKED_CELL_ROLE):
                    locked.append(group.child(p).text(0))
        assert sorted(locked) == sorted(
            permission_label(c) for c in (Permissions.ADMIN_MANAGE_USERS, Permissions.ADMIN_MANAGE_ROLES)
        )


class TestRoleNamesOnScreens:
    def test_users_table_and_user_dialog_picker(self, lang, qtbot, db_session):
        from cbpos.ui.views.user_view import UserDialog, UserView

        lang("si")
        users = [
            SimpleNamespace(id=1, username="nimal", role=ROLE_ROWS[1], role_id=2, is_active=True),
            SimpleNamespace(id=2, username="kamal", role=ROLE_ROWS[2], role_id=3, is_active=True),
        ]
        with (
            patch("cbpos.ui.views.user_view.UserService.get_all_users", return_value=users),
            patch("cbpos.ui.views.user_view.UserService.get_all_roles", return_value=ROLE_ROWS),
        ):
            view = UserView()
            qtbot.addWidget(view)
            view.load_users()
            dialog = UserDialog()
            qtbot.addWidget(dialog)

        assert view.table.item(0, 2).text() == display_role_name("Manager")
        assert view.table.item(1, 2).text() == "Supervisor"
        picker = [dialog.cmb_role.itemText(i) for i in range(dialog.cmb_role.count())]
        assert picker == [display_role_name("Admin"), display_role_name("Manager"), "Supervisor"]
        assert dialog.cmb_role.itemData(0) == 1

    def test_role_manager_list(self, lang, qtbot):
        from cbpos.ui.dialogs.role_manager import RoleManagerDialog

        lang("ta")
        with (
            patch("cbpos.ui.dialogs.role_manager.UserService.get_all_roles", return_value=ROLE_ROWS),
            patch("cbpos.ui.dialogs.role_manager.RoleService.get_user_count_for_role", return_value=0),
        ):
            dialog = RoleManagerDialog()
            qtbot.addWidget(dialog)

        names = [dialog.tree.topLevelItem(i).text(0) for i in range(dialog.tree.topLevelItemCount())]
        assert display_role_name("Manager") in names
        assert "Supervisor" in names
        assert any(n.startswith(display_role_name("Admin")) for n in names)
        assert not any(n.startswith("Admin") or n == "Manager" for n in names)

    def test_side_menu_role_line(self, lang, qtbot):
        from cbpos.ui.widgets.side_menu import SideMenu

        lang("si")
        menu = SideMenu()
        qtbot.addWidget(menu)
        menu.set_user(SimpleNamespace(id=7, username="nimal", role=SimpleNamespace(name="Cashier")))
        assert menu.lbl_role.text() == display_role_name("Cashier")
        assert not LATIN.search(menu.lbl_role.text())


class TestActivityLogEventColumn:
    def test_event_column_is_translated(self, lang, qtbot, db_session):
        from cbpos.ui.views.user_view import UserView

        lang("ta")
        log = SimpleNamespace(
            timestamp=datetime(2026, 10, 7, 9, 30),
            user=SimpleNamespace(username="nimal"),
            event_type="SECURITY",
            action="UPDATE_PERMISSIONS",
            terminal_id="TERM-01",
            details="",
        )
        with patch("cbpos.ui.views.user_view.UserService.get_recent_activity", return_value=[log]):
            view = UserView()
            qtbot.addWidget(view)
            view.load_logs()

        assert view.log_table.item(0, 2).text() == event_type_label("SECURITY")
        assert not LATIN.search(view.log_table.item(0, 2).text())
