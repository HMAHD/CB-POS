"""UI tests for ManagerOverrideDialog and ProfileDialog verifying session isolation."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.auth_service import AuthService
from cbpos.ui.dialogs.manager_override_dialog import ManagerOverrideDialog
from cbpos.ui.dialogs.profile_dialog import ProfileDialog

pytestmark = pytest.mark.usefixtures("qapp")


def test_manager_override_dialog_authenticates_without_session_switch(monkeypatch):
    """ManagerOverrideDialog calls authenticate_pin and preserves current user."""
    cashier = SimpleNamespace(id=1, username="cashier")
    manager = SimpleNamespace(id=2, username="manager")

    AuthService._current_user = cashier

    monkeypatch.setattr(
        AuthService,
        "authenticate_pin",
        lambda pin: manager if pin == "5678" else None,
    )
    monkeypatch.setattr(
        "cbpos.core.services.permission_service.PermissionService.user_has_permission",
        lambda user, perm: user.id == manager.id,
    )

    dialog = ManagerOverrideDialog("sales.void")
    dialog.pin_input.setText("5678")

    with patch.object(dialog, "accept") as mock_accept:
        dialog.verify_pin()
        assert mock_accept.called
        assert dialog.authorized_user == manager
        # Session is still cashier
        assert AuthService.get_current_user() == cashier

    AuthService._current_user = None


def test_manager_override_dialog_denies_unauthorized_user(monkeypatch):
    """ManagerOverrideDialog refuses PIN if user lacks required permission."""
    other_user = SimpleNamespace(id=3, username="other")
    monkeypatch.setattr(AuthService, "authenticate_pin", lambda pin: other_user)
    monkeypatch.setattr(
        "cbpos.core.services.permission_service.PermissionService.user_has_permission",
        lambda user, perm: False,
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    dialog = ManagerOverrideDialog("sales.void")
    dialog.pin_input.setText("1111")

    with patch.object(dialog, "accept") as mock_accept:
        dialog.verify_pin()
        assert not mock_accept.called
        assert dialog.authorized_user is None
        assert dialog.pin_input.text() == ""


def test_profile_dialog_checks_own_pin_without_session_switch(monkeypatch):
    """ProfileDialog uses check_own_pin and does not switch session on wrong/other user's PIN."""
    cashier = SimpleNamespace(id=1, username="cashier")
    AuthService._current_user = cashier

    check_own_pin_called_with = []

    def mock_check_own_pin(user_id, pin):
        check_own_pin_called_with.append((user_id, pin))
        return pin == "0000"

    monkeypatch.setattr(AuthService, "check_own_pin", mock_check_own_pin)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    mock_update_profile = MagicMock(return_value=True)
    monkeypatch.setattr(
        "cbpos.core.services.user_service.UserService.update_user_profile",
        mock_update_profile,
    )

    dialog = ProfileDialog()
    # Try with another user's PIN
    dialog.input_current_pin.setText("5678")
    dialog.update_profile()

    assert check_own_pin_called_with == [(1, "5678")]
    assert not mock_update_profile.called
    assert AuthService.get_current_user() == cashier

    # Try with own PIN
    check_own_pin_called_with.clear()
    dialog.input_current_pin.setText("0000")
    dialog.input_name.setText("Updated Cashier")
    with patch.object(dialog, "accept") as mock_accept:
        dialog.update_profile()
        assert check_own_pin_called_with == [(1, "0000")]
        assert mock_update_profile.called
        assert mock_accept.called
        assert AuthService.get_current_user() == cashier

    AuthService._current_user = None
