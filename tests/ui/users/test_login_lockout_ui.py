"""UI tests for login, manager override, and profile dialog lockout behaviour (#856)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.auth_service import AuthService
from cbpos.ui.dialogs.manager_override_dialog import ManagerOverrideDialog
from cbpos.ui.dialogs.profile_dialog import ProfileDialog
from cbpos.ui.views.login_view import LoginView

pytestmark = pytest.mark.usefixtures("qapp")


def test_login_view_lockout_disables_controls_and_counts_down(monkeypatch):
    """When locked out, LoginView disables input & keypad, shows countdown, and re-enables at 0."""
    view = LoginView()
    view.show()

    # Terminal is locked for 15 seconds
    monkeypatch.setattr(AuthService, "get_terminal_lockout_seconds", lambda: 15)

    view._set_locked_state(True, 15)

    assert not view.pin_input.isEnabled()
    for btn in view._numpad_buttons:
        assert not btn.isEnabled()
    assert not view.lbl_error.isHidden()
    assert "15" in view.lbl_error.text()

    # Tick timer down to 0
    monkeypatch.setattr(AuthService, "get_terminal_lockout_seconds", lambda: 0)
    view._on_lockout_tick()

    assert view.pin_input.isEnabled()
    for btn in view._numpad_buttons:
        assert btn.isEnabled()
    assert view.lbl_error.isHidden()


def test_login_view_shows_attempts_left_when_near_lockout(qtbot, monkeypatch):
    """When wrong PIN is entered and attempts remaining <= 2, attempts_left message is shown."""
    view = LoginView()
    view.show()

    monkeypatch.setattr(AuthService, "login", lambda pin: None)
    monkeypatch.setattr(AuthService, "get_terminal_lockout_seconds", lambda: 0)
    monkeypatch.setattr(AuthService, "get_terminal_failures_remaining", lambda: 2)

    view.pin_input.setText("1234")
    view.attempt_login()

    qtbot.waitUntil(lambda: not view.lbl_error.isHidden(), timeout=2000)
    assert "2" in view.lbl_error.text()


def test_manager_override_dialog_shows_locked_warning(monkeypatch):
    """ManagerOverrideDialog alerts user when terminal is locked out."""
    monkeypatch.setattr(AuthService, "get_terminal_lockout_seconds", lambda: 20)

    dialog = ManagerOverrideDialog("sales.void")
    dialog.pin_input.setText("1234")

    warning_mock = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warning_mock)

    dialog.verify_pin()

    assert warning_mock.called
    args = warning_mock.call_args[0]
    assert "20" in args[2]  # error message has seconds


def test_profile_dialog_shows_locked_warning(monkeypatch):
    """ProfileDialog alerts user when terminal is locked out."""
    user = SimpleNamespace(id=1, username="admin")
    monkeypatch.setattr(AuthService, "get_current_user", lambda: user)
    monkeypatch.setattr(AuthService, "get_terminal_lockout_seconds", lambda: 20)

    dialog = ProfileDialog()
    dialog.input_current_pin.setText("1234")

    warning_mock = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warning_mock)

    dialog.update_profile()

    assert warning_mock.called
    args = warning_mock.call_args[0]
    assert "20" in args[2]
