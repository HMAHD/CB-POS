"""UI tests for MainWindow session termination, modal closure, and cart auto-holding (#860)."""

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from cbpos.core.services.auth_service import AuthService
from cbpos.ui.main_window import MainWindow

pytestmark = [pytest.mark.usefixtures("qapp", "db_session")]


@pytest.fixture
def main_window(qapp, monkeypatch):
    """Fixture providing an initialized MainWindow instance."""
    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent: True,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)

    win = MainWindow()
    user = SimpleNamespace(id=1, username="test_cashier")
    win.user = user
    AuthService._current_user = user

    yield win

    win.watchdog.stop_monitoring()
    win.deleteLater()
    QApplication.processEvents()
    AuthService._current_user = None


def test_logout_closes_active_modal_dialog(main_window):
    """Calling logout closes any active modal dialog and lands on LoginView."""
    dlg = QDialog(main_window)
    dlg.open()
    assert dlg.isVisible()

    main_window.logout("LOGOUT")

    assert not dlg.isVisible()
    assert main_window.stack.currentWidget() == main_window.login_view


def test_timeout_closes_active_modal_dialog_and_logs_out(main_window):
    """Watchdog session_expired signal closes modal dialog and transitions to LoginView."""
    dlg = QDialog(main_window)
    dlg.open()
    assert dlg.isVisible()

    main_window.watchdog.session_expired.emit()

    assert not dlg.isVisible()
    assert main_window.stack.currentWidget() == main_window.login_view
    assert AuthService.get_current_user() is None


def test_logout_auto_holds_open_cart_and_shows_notice(main_window):
    """Logging out with cart items auto-holds the bill and shows notice on LoginView."""
    from decimal import Decimal

    product = SimpleNamespace(id=99, barcode="8608608608601", name_en="Held Product", price=Decimal("250.00"))
    main_window.sales_view.cart_service.add_item(product, qty=1)
    assert len(main_window.sales_view.cart_service.items) == 1

    main_window.logout("LOGOUT")

    assert len(main_window.sales_view.cart_service.items) == 0
    assert not main_window.login_view.lbl_info.isHidden()
    assert "F7" in main_window.login_view.lbl_info.text()

    # Successful login clears the notice
    main_window.login_view.clear_held_bill_notice()
    assert main_window.login_view.lbl_info.isHidden()
