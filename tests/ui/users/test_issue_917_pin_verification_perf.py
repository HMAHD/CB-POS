"""Regression tests for Issue #917 — PIN verification off the UI thread."""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QDialog

from cbpos.core.services.auth_service import AuthService
from cbpos.ui.dialogs.manager_override_dialog import ManagerOverrideDialog
from cbpos.ui.dialogs.profile_dialog import ProfileDialog
from cbpos.ui.views.login_view import LoginView


@pytest.fixture
def ten_users_hashes():
    """Return 10 users with PIN hashes."""
    users = []
    for i in range(10):
        # We don't need real bcrypt compute in tests; we can mock _verify_against_hash
        users.append(
            SimpleNamespace(
                id=i + 1,
                username=f"user_{i}",
                pin_hash=f"hash_{i}",
                is_active=True,
                role=SimpleNamespace(name="Cashier", access_level=1, permissions=[]),
            )
        )
    return users


def test_issue_917_login_does_not_block_ui_thread(qapp, qtbot, ten_users_hashes):
    """PIN login runs verification on worker thread; zero bcrypt calls on GUI thread (#917)."""
    gui_thread = threading.main_thread()
    threads_called = []
    worker_started_event = threading.Event()
    worker_release_event = threading.Event()

    def mock_match_active_user(session, pin):
        threads_called.append(threading.current_thread())
        worker_started_event.set()
        # Hold worker until test confirms UI remains responsive
        worker_release_event.wait(timeout=5.0)
        return None

    with patch.object(AuthService, "_match_active_user", side_effect=mock_match_active_user):
        view = LoginView()
        view.show()
        view.pin_input.setText("9999")

        # Trigger login
        view.attempt_login()

        # Wait until the worker starts and enters verification
        assert worker_started_event.wait(timeout=3.0)

        # While verification is running:
        # 1. Controls must be disabled
        assert not view.pin_input.isEnabled()
        for btn in view._numpad_buttons:
            assert not btn.isEnabled()

        # 2. GUI event processing remains responsive
        qapp.postEvent(view, QEvent(QEvent.Type.User))
        QApplication.processEvents()
        assert not view.pin_input.isEnabled()

        # Release worker
        worker_release_event.set()

        # Wait for worker completion
        qtbot.waitUntil(lambda: view.pin_input.isEnabled(), timeout=5000)

        # Controls restored
        assert view.pin_input.isEnabled()
        for btn in view._numpad_buttons:
            assert btn.isEnabled()

        # Verify threading: calls occurred, but NONE on GUI thread
        assert len(threads_called) > 0
        assert all(t is not gui_thread for t in threads_called)
        view.deleteLater()


def test_issue_917_override_dialog_uses_worker(qapp, qtbot):
    """ManagerOverrideDialog runs authenticate_pin on worker thread (#917)."""
    gui_thread = threading.main_thread()
    threads_called = []
    worker_release_event = threading.Event()

    manager = SimpleNamespace(
        id=2,
        username="manager",
        role=SimpleNamespace(name="Manager", access_level=5, permissions=[]),
    )

    def mock_authenticate(pin):
        threads_called.append(threading.current_thread())
        worker_release_event.wait(timeout=5.0)
        return manager if pin == "5678" else None

    with (
        patch.object(AuthService, "authenticate_pin", side_effect=mock_authenticate),
        patch("cbpos.core.services.permission_service.PermissionService.user_has_permission", return_value=True),
    ):
        dlg = ManagerOverrideDialog("sales.void")
        dlg.pin_input.setText("5678")

        dlg.verify_pin()

        # Controls disabled while checking
        assert not dlg.pin_input.isEnabled()
        assert not dlg.btn_verify.isEnabled()

        # Release worker
        worker_release_event.set()

        # Wait until dialog accepts
        qtbot.waitUntil(lambda: dlg.result() == QDialog.DialogCode.Accepted, timeout=5000)

        assert dlg.authorized_user == manager
        assert len(threads_called) == 1
        assert threads_called[0] is not gui_thread
        dlg.deleteLater()


def test_issue_917_profile_dialog_uses_worker(qapp, qtbot):
    """ProfileDialog runs check_own_pin on worker thread (#917)."""
    gui_thread = threading.main_thread()
    threads_called = []
    worker_release_event = threading.Event()
    user = SimpleNamespace(id=1, username="cashier")

    def mock_check_own(user_id, pin):
        threads_called.append(threading.current_thread())
        worker_release_event.wait(timeout=5.0)
        return pin == "1234"

    with (
        patch.object(AuthService, "get_current_user", return_value=user),
        patch.object(AuthService, "check_own_pin", side_effect=mock_check_own),
        patch("cbpos.core.services.user_service.UserService.update_user_profile", return_value=True),
        patch("cbpos.ui.dialogs.profile_dialog.QMessageBox"),
    ):
        dlg = ProfileDialog()
        dlg.input_current_pin.setText("1234")
        dlg.input_name.setText("cashier_new")

        dlg.update_profile()

        # Controls disabled while checking
        assert not dlg.input_current_pin.isEnabled()
        assert not dlg.btn_update.isEnabled()

        # Release worker
        worker_release_event.set()

        qtbot.waitUntil(lambda: dlg.result() == QDialog.DialogCode.Accepted, timeout=5000)

        assert len(threads_called) == 1
        assert threads_called[0] is not gui_thread
        dlg.deleteLater()


def test_issue_917_repeated_submit_does_not_start_parallel_checks(qapp, qtbot):
    """Clicking submit or pressing Enter while checking does not spawn parallel checks (#917)."""
    call_count = 0
    worker_release_event = threading.Event()

    def mock_match(session, pin):
        nonlocal call_count
        call_count += 1
        worker_release_event.wait(timeout=5.0)
        return None

    with patch.object(AuthService, "_match_active_user", side_effect=mock_match):
        view = LoginView()
        view.show()
        view.pin_input.setText("1111")

        view.attempt_login()
        # Repeated calls while running
        view.attempt_login()
        view.attempt_login()

        worker_release_event.set()
        qtbot.waitUntil(lambda: view.pin_input.isEnabled(), timeout=5000)

        assert call_count == 1
        view.deleteLater()


def test_issue_917_closing_dialog_while_worker_running_ignores_result(qapp, qtbot):
    """Closing or rejecting dialog while worker is running ignores the result safely (#917)."""
    worker_release_event = threading.Event()
    manager = SimpleNamespace(
        id=2,
        username="manager",
        role=SimpleNamespace(name="Manager", access_level=5, permissions=[]),
    )

    def mock_authenticate(pin):
        worker_release_event.wait(timeout=5.0)
        return manager

    with (
        patch.object(AuthService, "authenticate_pin", side_effect=mock_authenticate),
        patch("cbpos.core.services.permission_service.PermissionService.user_has_permission", return_value=True),
    ):
        dlg = ManagerOverrideDialog("sales.void")
        dlg.pin_input.setText("5678")
        dlg.verify_pin()

        # Close dialog before worker finishes
        dlg.reject()
        assert dlg.result() == QDialog.DialogCode.Rejected

        # Worker now finishes
        worker_release_event.set()

        # Dialog must NOT accept or resurrect
        QApplication.processEvents()
        assert dlg.authorized_user is None
        assert dlg.result() == QDialog.DialogCode.Rejected
        dlg.deleteLater()


def test_issue_917_ten_users_no_bcrypt_call_on_gui_thread(qapp, qtbot, ten_users_hashes):
    """With 10 users, no bcrypt verification call executes on the GUI thread (#917)."""
    gui_thread = threading.main_thread()
    gui_calls = []

    def mock_verify_against_hash(pin, pin_hash):
        if threading.current_thread() is gui_thread:
            gui_calls.append(True)
        return False

    with (
        patch.object(AuthService, "_is_terminal_locked", return_value=False),
        patch.object(AuthService, "_verify_against_hash", side_effect=mock_verify_against_hash),
        patch.object(AuthService, "_record_terminal_failure"),
    ):
        db_mock = MagicMock()
        db_mock.get_session.return_value.__enter__.return_value.query.return_value.options.return_value.filter.return_value.all.return_value = ten_users_hashes
        with patch("cbpos.core.services.auth_service.Database", return_value=db_mock):
            view = LoginView()
            view.show()
            view.pin_input.setText("0000")

            view.attempt_login()
            qtbot.waitUntil(lambda: view.pin_input.isEnabled(), timeout=5000)

            assert len(gui_calls) == 0
            view.deleteLater()
