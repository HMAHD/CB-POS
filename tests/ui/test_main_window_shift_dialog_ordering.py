"""
#526: on_login_success() opened StartShiftDialog (a modal, blocking .exec())
*before* switching self.stack to sales_view -- so for the entire time the
dialog was open, the login/PIN page was still the visually active page
underneath it. Fixed by switching to sales_view first.
"""

import pytest
from PyQt6.QtWidgets import QApplication

from cbpos.core.models import Permission, Role, User
from cbpos.ui.main_window import MainWindow

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"shift_order_test_{suffix}")
    role = Role(name=f"ShiftOrderRole_{suffix}", permissions=[permission])
    user = User(username=f"shift_order_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def window(qapp, db_session):
    w = MainWindow()
    yield w
    w.deleteLater()
    # SettingsPage's own QTimer.singleShot(0, ...) height-fix touches
    # widgets that only exist while this window is alive -- flush it here,
    # inside this window's own teardown, rather than letting it fire later
    # against a *different* MainWindow's already-deleted widgets.
    QApplication.processEvents()


class TestStartShiftDialogAppearsOverSales:
    def test_sales_view_is_current_before_the_shift_dialog_is_shown(self, window, db_session, test_user, monkeypatch):
        monkeypatch.setattr(
            "cbpos.ui.main_window.ShiftService.get_current_shift",
            lambda self, user_id: None,
        )

        captured = {}

        def fake_exec(self):
            captured["current_widget"] = window.stack.currentWidget()
            return 0

        monkeypatch.setattr("cbpos.ui.main_window.StartShiftDialog.exec", fake_exec)

        window.on_login_success(test_user)

        assert captured["current_widget"] is window.sales_view

    def test_no_open_shift_needed_still_lands_on_sales_view(self, window, db_session, test_user, monkeypatch):
        monkeypatch.setattr(
            "cbpos.ui.main_window.ShiftService.get_current_shift",
            lambda self, user_id: object(),  # any truthy "shift already open" value
        )

        window.on_login_success(test_user)

        assert window.stack.currentWidget() is window.sales_view
