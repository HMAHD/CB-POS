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


def test_profile_dialog_duplicate_pin_shows_warning(monkeypatch):
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
        assert not mock_accept.called
        assert len(warning_box) == 1
        assert "That PIN can't be used" in warning_box[0][1]

    AuthService._current_user = None
