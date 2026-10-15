"""
#535 (REC-01): after adding an item, selecting a customer or completing a
sale, the search box must have focus so the cashier stays on the keyboard
between scans. Each test first parks focus on another control (the way a
mouse click on Pay or a customer button does), then runs the path.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from cbpos.core.models import Customer
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views import sales_view as sales_view_module
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session, monkeypatch):
    monkeypatch.setattr(sales_view_module, "receipt_printer_configured", lambda: True)
    v = SalesView()
    v.resize(1366, 768)
    v.show()
    QTest.qWaitForWindowExposed(v)
    yield v
    v.hide()
    v.deleteLater()


def _park_focus_elsewhere(view: SalesView) -> None:
    view.action_panel.btn_pay.setFocus()
    assert view.focusWidget() is view.action_panel.btn_pay


def _search_has_focus(view: SalesView) -> bool:
    return view.focusWidget() is view.barcode_input


def _product(price: str = "100.00") -> MagicMock:
    product = MagicMock()
    product.id = 1
    product.name_en = "Focus Product"
    product.barcode = "FOCUS001"
    product.price = Decimal(price)
    product.stock_qty = Decimal("10")
    product.unit = None
    product.is_age_restricted = False
    return product


def _fake_dialog_cls(accept: bool = True, **attrs) -> MagicMock:
    dialog = MagicMock()
    dialog.exec.return_value = 1 if accept else 0
    for name, value in attrs.items():
        setattr(dialog, name, value)
    return MagicMock(return_value=dialog)


class TestAddingAnItemReturnsFocusToSearch:
    def test_scan_that_opens_the_quantity_dialog(self, view, monkeypatch):
        monkeypatch.setattr(view.product_service, "search_products", lambda *a, **k: [_product()])
        monkeypatch.setattr(
            sales_view_module, "QuantityDialog", _fake_dialog_cls(get_quantity=MagicMock(return_value=Decimal("1")))
        )
        _park_focus_elsewhere(view)

        view.process_barcode_external("FOCUS001")

        assert len(view.cart_service.items) == 1
        assert _search_has_focus(view)

    def test_selecting_a_product_in_advanced_search(self, view, monkeypatch):
        monkeypatch.setattr(
            sales_view_module, "QuantityDialog", _fake_dialog_cls(get_quantity=MagicMock(return_value=Decimal("2")))
        )
        _park_focus_elsewhere(view)

        view.on_advanced_search_product_selected(_product())

        assert len(view.cart_service.items) == 1
        assert _search_has_focus(view)


class TestSelectingACustomerReturnsFocusToSearch:
    def test_customer_dialog(self, view, db_session, monkeypatch):
        customer = Customer(name="Dialog Customer", phone="0710000001")
        db_session.add(customer)
        db_session.flush()
        monkeypatch.setattr(sales_view_module, "CustomerSelectionDialog", _fake_dialog_cls(selected_customer=customer))
        _park_focus_elsewhere(view)

        view.select_customer()

        assert view.customer is customer
        assert _search_has_focus(view)

    def test_loyalty_card_scan(self, view, db_session):
        customer = Customer(name="Card Customer", phone="0710000002", loyalty_card_code="CARD-FOCUS-535")
        db_session.add(customer)
        db_session.commit()
        _park_focus_elsewhere(view)

        view.process_barcode_external("CARD-FOCUS-535")

        assert view.customer is not None and view.customer.id == customer.id
        assert _search_has_focus(view)

    def test_clearing_the_customer_with_the_clear_button(self, view, db_session):
        customer = Customer(name="Clear Me", phone="0710000003")
        db_session.add(customer)
        db_session.flush()
        view.set_customer(customer)
        QTest.mouseClick(view.action_panel.btn_cust_clear, Qt.MouseButton.LeftButton)

        assert view.customer is None
        assert _search_has_focus(view)


class TestCompletingASaleReturnsFocusToSearch:
    def test_payment_dialog_confirmed(self, view, monkeypatch):
        view.cart_service.add_item(_product(), qty=Decimal("1"))
        view.update_cart_display()
        monkeypatch.setattr(
            sales_view_module, "PaymentDialog", _fake_dialog_cls(payment_data=([{"method": "CASH"}], None))
        )
        monkeypatch.setattr(sales_view_module.TransactionService, "process_sale", lambda *a, **k: MagicMock())
        monkeypatch.setattr(sales_view_module.ConfigService, "get", lambda *a, **k: False)
        _park_focus_elsewhere(view)

        view.process_payment()

        assert view.cart_service.items == []
        assert _search_has_focus(view)

    def test_payment_dialog_cancelled(self, view, monkeypatch):
        view.cart_service.add_item(_product(), qty=Decimal("1"))
        view.update_cart_display()
        monkeypatch.setattr(sales_view_module, "PaymentDialog", _fake_dialog_cls(accept=False))
        _park_focus_elsewhere(view)

        view.process_payment()

        assert _search_has_focus(view)

    def test_pay_on_an_empty_cart(self, view):
        _park_focus_elsewhere(view)

        view.process_payment()

        assert _search_has_focus(view)

    def test_quick_pay_when_disabled(self, view, monkeypatch):
        monkeypatch.setattr(sales_view_module.ConfigService, "get", lambda *a, **k: False)
        monkeypatch.setattr(sales_view_module.QMessageBox, "information", lambda *a, **k: None)
        _park_focus_elsewhere(view)

        view.quick_pay()

        assert _search_has_focus(view)


class TestSwitchingOrdersReturnsFocusToSearch:
    def test_switching_to_a_held_order_tab(self, view, monkeypatch):
        monkeypatch.setattr(sales_view_module.SuspendedTransactionService, "recall_bill", lambda *a, **k: True)
        _park_focus_elsewhere(view)

        view.switch_to_order(7)

        assert _search_has_focus(view)

    def test_new_order_tab_while_the_cart_has_items(self, view, monkeypatch):
        view.cart_service.add_item(_product(), qty=Decimal("1"))
        monkeypatch.setattr(sales_view_module.SuspendedTransactionService, "hold_bill", lambda *a, **k: 1)
        _park_focus_elsewhere(view)

        view.create_new_order()

        assert view.cart_service.items == []
        assert _search_has_focus(view)


class TestNoFocusStealWhileADialogIsOpen:
    def test_selecting_from_advanced_search_leaves_the_open_dialog_alone(self, view, monkeypatch):
        """Advanced search stays open after a pick; the search box takes focus once it closes."""
        from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit

        dialog = QDialog(view)
        dialog_field = QLineEdit(dialog)
        dialog.setModal(True)
        dialog.show()
        dialog_field.setFocus()
        monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: dialog))
        monkeypatch.setattr(
            sales_view_module, "QuantityDialog", _fake_dialog_cls(get_quantity=MagicMock(return_value=Decimal("1")))
        )
        _park_focus_elsewhere(view)

        view.on_advanced_search_product_selected(_product())

        assert view.focusWidget() is view.action_panel.btn_pay
        dialog.hide()
        dialog.deleteLater()
