"""UI tests for Issue #854: F12 Quick Pay uses the default cash method."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cbpos.core.models import PaymentMethod, Product
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views import sales_view as sales_view_module
from cbpos.ui.views.sales_view import SalesView

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.ui]


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


def test_quick_pay_uses_default_cash_method(view, db_session, monkeypatch):
    """quick_pay resolves the default cash method and uses its name."""
    product = Product(
        name_en="Quick Pay Item",
        barcode="QP01",
        price=Decimal("150.00"),
        stock_qty=Decimal("10.000"),
    )
    view.cart_service.add_item(product, qty=Decimal("1.000"))

    custom_cash = PaymentMethod(name="Cash LKR", kind="CASH", is_cash=True, is_active=True)
    monkeypatch.setattr(
        sales_view_module.ConfigService, "get", lambda k, *a, **kw: True if k == "quick_pay_enabled" else None
    )
    monkeypatch.setattr(sales_view_module.PaymentService, "get_default_cash_method", lambda: custom_cash)

    process_mock = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(sales_view_module.TransactionService, "process_sale", process_mock)

    view.quick_pay()

    process_mock.assert_called_once()
    _cart, payments, _customer_id = process_mock.call_args[0]
    assert payments == [{"method": "Cash LKR", "amount": Decimal("150.00")}]


def test_quick_pay_warns_when_no_active_cash_method(view, monkeypatch):
    """quick_pay warns and aborts when no active cash payment method is configured."""
    product = Product(
        name_en="Quick Pay Item",
        barcode="QP02",
        price=Decimal("150.00"),
        stock_qty=Decimal("10.000"),
    )
    view.cart_service.add_item(product, qty=Decimal("1.000"))

    monkeypatch.setattr(
        sales_view_module.ConfigService, "get", lambda k, *a, **kw: True if k == "quick_pay_enabled" else None
    )
    monkeypatch.setattr(sales_view_module.PaymentService, "get_default_cash_method", lambda: None)

    warning_mock = MagicMock()
    monkeypatch.setattr(sales_view_module.QMessageBox, "warning", warning_mock)
    process_mock = MagicMock()
    monkeypatch.setattr(sales_view_module.TransactionService, "process_sale", process_mock)

    view.quick_pay()

    process_mock.assert_not_called()
    warning_mock.assert_called_once()
