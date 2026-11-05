"""UI tests for Issue #892: Unexpected checkout error fails silently.

Verifies that when process_sale encounters an OperationalError or unexpected error:
1. Critical QMessageBox is displayed with clear warning and reason.
2. The cart and applied payments are preserved.
3. The payment dialog remains open and interactive so the cashier does not hand over goods.
"""

from decimal import Decimal

import pytest
from sqlalchemy.exc import OperationalError

from cbpos.core.models import PaymentMethod, Product
from cbpos.i18n import _t
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


def test_sales_view_shows_error_when_process_sale_raises(view, monkeypatch):
    """When quick_pay encounters an OperationalError, critical QMessageBox is shown and cart is kept."""
    product = Product(
        name_en="Test Checkout Item",
        barcode="CHK01",
        price=Decimal("250.00"),
        stock_qty=Decimal("10.000"),
    )
    view.cart_service.add_item(product, qty=Decimal("1.000"))
    assert len(view.cart_service.items) == 1

    custom_cash = PaymentMethod(name="Cash LKR", kind="CASH", is_cash=True, is_active=True)
    monkeypatch.setattr(
        sales_view_module.ConfigService, "get", lambda k, *a, **kw: True if k == "quick_pay_enabled" else None
    )
    monkeypatch.setattr(sales_view_module.PaymentService, "get_default_cash_method", lambda: custom_cash)

    critical_boxes = []
    monkeypatch.setattr(
        sales_view_module.QMessageBox, "critical", lambda parent, title, text: critical_boxes.append((title, text))
    )

    def raise_operational_error(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("database locked"))

    monkeypatch.setattr(sales_view_module.TransactionService, "process_sale", raise_operational_error)

    view.quick_pay()

    # Critical message box was shown
    assert len(critical_boxes) == 1
    title, message = critical_boxes[0]
    assert title == _t("common.error")
    assert _t("errors.db_connection_lost") in message
    assert "NOT saved" in message or "නැහැ" in message or "சேமிக்கப்படவில்லை" in message

    # Cart is kept intact!
    assert len(view.cart_service.items) == 1


def test_payment_dialog_keeps_payments_and_stays_open_on_sale_error(view, monkeypatch):
    """When PaymentDialog finishes but process_sale fails, dialog stays open and payments are kept."""
    product = Product(
        name_en="Test Dialog Item",
        barcode="CHK02",
        price=Decimal("500.00"),
        stock_qty=Decimal("10.000"),
    )
    view.cart_service.add_item(product, qty=Decimal("1.000"))

    critical_boxes = []
    monkeypatch.setattr(
        sales_view_module.QMessageBox, "critical", lambda parent, title, text: critical_boxes.append((title, text))
    )

    def raise_db_error(*args, **kwargs):
        raise OperationalError("INSERT INTO sales", {}, Exception("disk I/O error"))

    monkeypatch.setattr(sales_view_module.TransactionService, "process_sale", raise_db_error)

    # We will simulate dialog interaction
    dlg = None

    orig_payment_dialog = sales_view_module.PaymentDialog

    def capture_dlg(*args, **kwargs):
        nonlocal dlg
        dlg = orig_payment_dialog(*args, **kwargs)
        # Instead of blocking exec(), simulate adding payment and clicking finish
        cash_method = dlg.payment_methods[0]
        dlg.select_method(cash_method, dlg._method_buttons[0][0])
        dlg.txt_amount.setText("500.00")
        dlg.add_payment()
        assert len(dlg.payments) == 1

        def fake_exec():
            # Trigger finish
            dlg._finish_sale()
            return 0

        dlg.exec = fake_exec
        return dlg

    monkeypatch.setattr(sales_view_module, "PaymentDialog", capture_dlg)

    view.process_payment()

    assert dlg is not None
    # Dialog finish button must be re-enabled after failure
    assert dlg.btn_finish.isEnabled() is True
    # Applied payment must still be there
    assert len(dlg.payments) == 1
    assert dlg.payments[0]["amount"] == Decimal("500.00")
    # Critical error message was shown
    assert len(critical_boxes) == 1
    assert _t("errors.db_connection_lost") in critical_boxes[0][1]
    # Cart still has the item
    assert len(view.cart_service.items) == 1
