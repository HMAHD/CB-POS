"""
#593 (UI-028-A): opening a customer in the Credit Book had no visible hint,
and a right-click menu must act on the row that was clicked -- the action
methods read ``self.selected_customer``, which was the *last opened*
customer and survived "Back", so a naive menu would take a payment for the
wrong person.
"""

from decimal import Decimal

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu

from cbpos.core.models import Customer
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.scanner import BarcodeScanner
from cbpos.ui.views.credit_book_view import CreditBookView

pytestmark = pytest.mark.usefixtures("qapp")


def _customer(db_session, name: str, phone: str, debt: str = "0.00") -> Customer:
    customer = Customer(name=name, phone=phone, current_debt=Decimal(debt), credit_limit=Decimal("10000.00"))
    db_session.add(customer)
    db_session.flush()
    return customer


@pytest.fixture
def view(db_session):
    v = CreditBookView()
    v.resize(1100, 650)
    v.show()
    v.activateWindow()
    QTest.qWaitForWindowActive(v)
    yield v
    v.hide()
    v.deleteLater()


def _row_of(view: CreditBookView, customer: Customer) -> int:
    for r in range(view.customer_table.rowCount()):
        item = view.customer_table.item(r, 0)
        if item and item.text() == str(customer.id):
            return r
    raise AssertionError(f"customer {customer.id} not in the list")


def _right_click_row(view: CreditBookView, row: int) -> None:
    """Emit the table's context-menu request at the centre of ``row`` (viewport coordinates)."""
    rect = view.customer_table.visualRect(view.customer_table.model().index(row, 1))
    view.customer_table.customContextMenuRequested.emit(rect.center())


def _menu_picks(monkeypatch, text: str | None, seen: dict | None = None) -> None:
    """Make QMenu.exec trigger the action labelled ``text`` (or none), recording every action's state."""

    def fake_exec(menu: QMenu, *args, **kwargs):
        chosen = None
        for action in menu.actions():
            if seen is not None:
                seen[action.text()] = action.isEnabled()
            if action.text() == text:
                chosen = action
        if chosen is not None and chosen.isEnabled():
            chosen.trigger()
        return chosen

    monkeypatch.setattr(QMenu, "exec", fake_exec)


@pytest.fixture
def allow_everything(monkeypatch):
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: object())


class TestContextMenuActsOnTheClickedCustomer:
    def test_receive_payment_after_back_goes_to_the_right_clicked_customer(
        self, view, db_session, monkeypatch, allow_everything
    ):
        a = _customer(db_session, "Customer A", "0711000001", debt="500.00")
        b = _customer(db_session, "Customer B", "0711000002", debt="300.00")
        view.load_customers()

        view._open_customer_row(_row_of(view, a))
        view.btn_back.click()

        paid_for: list[int] = []

        class FakeReceivePaymentDialog:
            def __init__(self, customer_id, parent=None):
                paid_for.append(customer_id)

            def exec(self):
                return 0

        monkeypatch.setattr("cbpos.ui.dialogs.receive_payment_dialog.ReceivePaymentDialog", FakeReceivePaymentDialog)
        _menu_picks(monkeypatch, _t("credit_book.btn_receive_payment"))

        _right_click_row(view, _row_of(view, b))

        assert paid_for == [b.id]

    def test_open_ledger_from_the_menu_opens_the_clicked_customer(self, view, db_session, monkeypatch):
        _customer(db_session, "First", "0711000003")
        target = _customer(db_session, "Second", "0711000004")
        view.load_customers()
        _menu_picks(monkeypatch, _t("credit_book.btn_open_customer_ledger"))

        _right_click_row(view, _row_of(view, target))

        assert view.stack.currentIndex() == 1
        assert view.selected_customer.id == target.id

    def test_edit_from_the_menu_edits_the_clicked_customer(self, view, db_session, monkeypatch):
        target = _customer(db_session, "Edit Target", "0711000005")
        view.load_customers()
        edited: list[int] = []

        class FakeEditor:
            def __init__(self, customer=None, parent=None):
                edited.append(customer.id)

            def exec(self):
                return 0

        monkeypatch.setattr("cbpos.ui.views.credit_book_view.CustomerEditor", FakeEditor)
        _menu_picks(monkeypatch, _t("credit_book.btn_edit_customer"))

        _right_click_row(view, _row_of(view, target))

        assert edited == [target.id]

    def test_right_click_selects_the_clicked_row(self, view, db_session, monkeypatch):
        _customer(db_session, "Row One", "0711000006")
        target = _customer(db_session, "Row Two", "0711000007")
        view.load_customers()
        _menu_picks(monkeypatch, None)

        row = _row_of(view, target)
        _right_click_row(view, row)

        assert view.customer_table.currentRow() == row

    def test_receive_payment_is_disabled_for_a_customer_with_no_debt(self, view, db_session, monkeypatch):
        clear = _customer(db_session, "Paid Up", "0711000008", debt="0.00")
        view.load_customers()
        seen: dict[str, bool] = {}
        _menu_picks(monkeypatch, None, seen)

        _right_click_row(view, _row_of(view, clear))

        assert seen[_t("credit_book.btn_receive_payment")] is False
        assert seen[_t("credit_book.btn_open_customer_ledger")] is True

    def test_right_click_on_empty_space_shows_no_menu(self, view, db_session, monkeypatch):
        view.load_customers()
        shown: list[int] = []
        monkeypatch.setattr(QMenu, "exec", lambda *a, **k: shown.append(1))

        bottom = view.customer_table.viewport().rect().bottomLeft()
        bottom.setY(bottom.y() - 1)
        view.customer_table.customContextMenuRequested.emit(bottom)

        assert shown == []


class TestBackForgetsTheCustomer:
    def test_back_clears_the_selected_customer(self, view, db_session):
        a = _customer(db_session, "Gone After Back", "0711000009")
        view.load_customers()
        view._open_customer_row(_row_of(view, a))

        view.btn_back.click()

        assert view.selected_customer is None


class TestOpeningIsDiscoverable:
    def test_rows_carry_an_open_hint(self, view, db_session):
        a = _customer(db_session, "Hinted", "0711000010")
        view.load_customers()

        assert view.customer_table.item(_row_of(view, a), 1).toolTip() == _t("credit_book.row_open_hint")

    def test_a_visible_hint_sits_next_to_the_open_button(self, view):
        assert view.lbl_open_hint.isVisible()
        assert view.lbl_open_hint.text() == _t("credit_book.row_open_hint")

    def test_rows_show_a_pointing_hand(self, view):
        assert view.customer_table.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor


class TestEnterOpensOnlyFromTheTable:
    def test_enter_on_the_table_opens_the_selected_customer(self, view, db_session):
        a = _customer(db_session, "Enter Me", "0711000011")
        view.load_customers()
        view.customer_table.setCurrentCell(_row_of(view, a), 1)
        view.customer_table.setFocus()

        QTest.keyClick(view.customer_table, Qt.Key.Key_Return)

        assert view.stack.currentIndex() == 1
        assert view.selected_customer.id == a.id

    def test_enter_in_the_search_box_does_not_open_a_customer(self, view, db_session):
        a = _customer(db_session, "Not Via Search", "0711000012")
        view.load_customers()
        view.customer_table.setCurrentCell(_row_of(view, a), 1)
        view.search_input.setFocus()

        QTest.keyClick(view.search_input, Qt.Key.Key_Return)

        assert view.stack.currentIndex() == 0

    def test_a_scan_on_the_table_is_routed_as_a_scan_not_an_open(self, view, db_session):
        a = _customer(db_session, "Scan Bystander", "0711000013")
        view.load_customers()
        view.customer_table.setCurrentCell(_row_of(view, a), 1)
        view.customer_table.setFocus()
        app = QApplication.instance()
        scanner = BarcodeScanner(app)
        scans: list[str] = []
        scanner.barcode_scanned.connect(scans.append)
        try:
            QTest.keyClicks(view.customer_table, "4791234567890")
            QTest.keyClick(view.customer_table, Qt.Key.Key_Return)
        finally:
            app.removeEventFilter(scanner)

        assert scans == ["4791234567890"]
        assert view.stack.currentIndex() == 0
