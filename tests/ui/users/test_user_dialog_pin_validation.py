"""UI tests for UserDialog and ProfileDialog duplicate PIN and reactivation handling."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.auth_service import AuthService
from cbpos.ui.dialogs.profile_dialog import ProfileDialog
from cbpos.ui.dialogs.user_dialog import UserDialog

pytestmark = pytest.mark.usefixtures("qapp")


def test_user_dialog_duplicate_pin_shows_warning_and_focuses(monkeypatch):
    """UserDialog shows warning and keeps dialog open when PIN is in use."""
    warning_box = []

    def mock_warning(parent, title, text):
        warning_box.append((title, text))

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.get_all_roles",
        lambda: [SimpleNamespace(id=1, name="Cashier")],
    )
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.create_user",
        MagicMock(side_effect=ValueError("pin_in_use")),
    )

    dialog = UserDialog()
    dialog.show()
    dialog.txt_username.setText("new_user")
    dialog.txt_pin.setText("1234")

    with patch.object(dialog, "accept") as mock_accept:
        dialog.save()
        assert not mock_accept.called
        assert len(warning_box) == 1
        assert "That PIN can't be used" in warning_box[0][1]


def test_user_dialog_reactivation_requires_pin(monkeypatch):
    """UserDialog shows warning when reactivating an inactive user without a PIN."""
    warning_box = []

    def mock_warning(parent, title, text):
        warning_box.append((title, text))

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.get_all_roles",
        lambda: [SimpleNamespace(id=1, name="Cashier")],
    )
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.update_user",
        MagicMock(side_effect=ValueError("pin_required_on_reactivate")),
    )

    existing_user = SimpleNamespace(id=5, username="inactive_user", role=None, role_id=1, is_active=False)
    dialog = UserDialog(user=existing_user)
    dialog.show()
    dialog.chk_active.setChecked(True)
    dialog.txt_pin.setText("")

    with patch.object(dialog, "accept") as mock_accept:
        dialog.save()
        assert not mock_accept.called
        assert len(warning_box) == 1
        assert "Enter a new PIN to turn this user back on" in warning_box[0][1]


def test_profile_dialog_duplicate_pin_shows_warning(qtbot, monkeypatch):
    """ProfileDialog shows warning and keeps dialog open when new PIN is already in use."""
    user = SimpleNamespace(id=2, username="cashier")
    AuthService._current_user = user

    warning_box = []

    def mock_warning(parent, title, text):
        warning_box.append((title, text))

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    monkeypatch.setattr(AuthService, "check_own_pin", lambda uid, pin: True)
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.update_user_profile",
        MagicMock(side_effect=ValueError("pin_in_use")),
    )

    dialog = ProfileDialog()
    dialog.show()
    dialog.input_current_pin.setText("0000")
    dialog.input_new_pin.setText("1234")

    with patch.object(dialog, "accept") as mock_accept:
        dialog.update_profile()
        qtbot.waitUntil(lambda: len(warning_box) == 1, timeout=2000)
        assert not mock_accept.called
        assert len(warning_box) == 1
        assert "That PIN can't be used" in warning_box[0][1]

    AuthService._current_user = None


def test_user_dialog_last_admin_controls_disabled_with_tooltip(monkeypatch):
    """When editing the sole active Admin, role and active controls are disabled with tooltip."""
    from cbpos.i18n import _t

    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.get_all_roles",
        lambda: [SimpleNamespace(id=1, name="Admin"), SimpleNamespace(id=2, name="Cashier")],
    )
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.is_last_active_admin",
        lambda user_id: user_id == 1,
    )

    admin_user = SimpleNamespace(id=1, username="admin", role=None, role_id=1, is_active=True)
    dialog = UserDialog(user=admin_user)
    dialog.show()

    assert not dialog.cmb_role.isEnabled()
    assert not dialog.chk_active.isEnabled()
    expected_tooltip = _t("users.last_admin")
    assert dialog.cmb_role.toolTip() == expected_tooltip
    assert dialog.chk_active.toolTip() == expected_tooltip


def test_user_dialog_last_admin_save_rejection_shows_warning(monkeypatch):
    """UserDialog shows warning when update_user raises ValueError('last_admin')."""
    from cbpos.i18n import _t

    warning_box = []

    def mock_warning(parent, title, text):
        warning_box.append((title, text))

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.get_all_roles",
        lambda: [SimpleNamespace(id=1, name="Admin"), SimpleNamespace(id=2, name="Cashier")],
    )
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.is_last_active_admin",
        lambda user_id: False,  # Simulate bypass of UI disablement
    )
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.update_user",
        MagicMock(side_effect=ValueError("last_admin")),
    )

    admin_user = SimpleNamespace(id=1, username="admin", role=None, role_id=1, is_active=True)
    dialog = UserDialog(user=admin_user)
    dialog.show()

    with patch.object(dialog, "accept") as mock_accept:
        dialog.save()
        assert not mock_accept.called
        assert len(warning_box) == 1
        assert _t("users.last_admin") in warning_box[0][1]


def test_user_dialog_non_admin_cannot_see_admin_role_in_create_mode(monkeypatch):
    """A non-Admin actor does not see the Admin role in cmb_role when creating a user."""
    monkeypatch.setattr(
        AuthService,
        "get_current_user",
        lambda: SimpleNamespace(id=2, username="manager", role=SimpleNamespace(name="Manager"), role_id=2),
    )
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.get_all_roles",
        lambda: [
            SimpleNamespace(id=1, name="Admin"),
            SimpleNamespace(id=2, name="Manager"),
            SimpleNamespace(id=3, name="Cashier"),
        ],
    )

    dialog = UserDialog()
    dialog.show()

    role_ids = [dialog.cmb_role.itemData(i) for i in range(dialog.cmb_role.count())]
    assert 1 not in role_ids
    assert 2 in role_ids
    assert 3 in role_ids


def test_user_dialog_editing_self_disables_role_combo(monkeypatch):
    """A user editing their own account has the role dropdown disabled with a tooltip."""
    from cbpos.i18n import _t

    current_user = SimpleNamespace(id=2, username="manager", role=SimpleNamespace(name="Manager"), role_id=2)
    monkeypatch.setattr(AuthService, "get_current_user", lambda: current_user)
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.get_all_roles",
        lambda: [SimpleNamespace(id=2, name="Manager"), SimpleNamespace(id=3, name="Cashier")],
    )
    monkeypatch.setattr("cbpos.core.services.user_service.UserService.is_last_active_admin", lambda uid: False)

    target_user = SimpleNamespace(
        id=2, username="manager", role=SimpleNamespace(name="Manager"), role_id=2, is_active=True
    )
    dialog = UserDialog(user=target_user)
    dialog.show()

    assert not dialog.cmb_role.isEnabled()
    assert dialog.cmb_role.toolTip() == _t("users.cannot_change_own_role")


def test_user_dialog_non_admin_editing_admin_disables_all_fields(monkeypatch):
    """A non-Admin attempting to edit an Admin user sees all fields and save button disabled with tooltip."""
    from cbpos.i18n import _t

    current_user = SimpleNamespace(id=2, username="manager", role=SimpleNamespace(name="Manager"), role_id=2)
    monkeypatch.setattr(AuthService, "get_current_user", lambda: current_user)
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.get_all_roles",
        lambda: [SimpleNamespace(id=1, name="Admin"), SimpleNamespace(id=2, name="Manager")],
    )
    monkeypatch.setattr("cbpos.core.services.user_service.UserService.is_last_active_admin", lambda uid: False)

    admin_user = SimpleNamespace(id=1, username="admin", role=SimpleNamespace(name="Admin"), role_id=1, is_active=True)
    dialog = UserDialog(user=admin_user)
    dialog.show()

    assert not dialog.txt_username.isEnabled()
    assert not dialog.txt_pin.isEnabled()
    assert not dialog.cmb_role.isEnabled()
    assert not dialog.chk_active.isEnabled()
    assert dialog.txt_username.toolTip() == _t("users.only_admin_can_modify_admin")
