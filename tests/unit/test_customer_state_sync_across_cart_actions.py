"""
Customer selection lived in two places that never stayed in sync:
SalesView.customer (used for the action panel display and the
resulting Sale's own customer_id) and CartService._customer (used for
customer-specific pricing). Selecting a customer via the normal
"Customer" button never called CartService.set_customer(), so
customer-specific price-list pricing silently never applied during a
normal checkout even with a customer selected.

Separately, Hold and Void cleared the cart but left the action panel
still showing the previous customer, and held bills never remembered
which customer they were for at all, so recalling one could never
restore it.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.models import Customer, Product
from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views import sales_view as sales_view_module
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


def _make_customer(db_session, name="Saman Kumara"):
    customer = Customer(name=name, phone=f"07{_next_suffix()}", loyalty_points=320)
    db_session.add(customer)
    db_session.flush()
    return customer


def _make_real_product(db_session, price="200.00"):
    product = Product(
        name_en="Test Product",
        barcode=f"TESTSYNC{_next_suffix()}",
        price=Decimal(price),
        stock_qty=Decimal("10"),
    )
    db_session.add(product)
    db_session.flush()
    return product


def _make_mock_product(price="200.00"):
    product = MagicMock()
    product.id = 1
    product.name_en = "Test Product"
    product.barcode = "TEST001"
    product.price = Decimal(price)
    product.stock_qty = Decimal("10")
    product.unit = None
    return product


class TestSetCustomerSyncsCartService:
    def test_selecting_a_customer_attaches_it_to_cart_service(self, view, db_session):
        customer = _make_customer(db_session)

        view.set_customer(customer)

        assert view.cart_service.get_customer() is customer

    def test_clearing_the_customer_also_clears_cart_service(self, view, db_session):
        customer = _make_customer(db_session)
        view.set_customer(customer)

        view.clear_customer()

        assert view.cart_service.get_customer() is None
        assert view.customer is None


class TestHoldAndVoidResetCustomerToWalkIn:
    def test_hold_bill_clears_the_selected_customer(self, view, db_session):
        customer = _make_customer(db_session)
        view.set_customer(customer)
        view.cart_service.add_item(_make_mock_product())
        view.update_cart_display()

        with patch.object(SuspendedTransactionService, "hold_bill", return_value=1):
            with patch.object(sales_view_module.QMessageBox, "information"):
                view.hold_bill()

        assert view.customer is None
        assert view.cart_service.get_customer() is None

    def test_void_bill_clears_the_selected_customer(self, view, db_session, monkeypatch):
        from cbpos.core.models import User
        import cbpos.core.utils.permission_helper as permission_helper

        manager = User(username="mgr_sync", pin_hash="x", role_id=None, is_active=True)
        manager.id = 99
        monkeypatch.setattr(permission_helper, "check_permission_with_override", lambda perm, parent: manager)

        customer = _make_customer(db_session)
        view.set_customer(customer)
        view.cart_service.add_item(_make_mock_product())
        view.update_cart_display()

        with patch.object(
            sales_view_module.QMessageBox, "question", return_value=sales_view_module.QMessageBox.StandardButton.Yes
        ):
            with patch("cbpos.ui.views.sales_view.LoggingService.log_action"):
                view.void_bill()

        assert view.customer is None
        assert view.cart_service.get_customer() is None


class TestHoldAndRecallRoundTripTheCustomer:
    def test_recalling_a_held_bill_restores_its_customer(self, view, db_session):
        customer = _make_customer(db_session)
        product = _make_real_product(db_session)
        view.set_customer(customer)
        view.cart_service.add_item(product)

        held_id = SuspendedTransactionService.hold_bill(view.cart_service)
        view.cart_service.clear()
        view.clear_customer()
        assert view.customer is None

        with patch.object(sales_view_module.QMessageBox, "information"):
            with patch.object(SuspendedTransactionService, "get_latest_suspended") as mock_latest:
                mock_latest.return_value = MagicMock(id=held_id)
                view.recall_bill()

        assert view.customer is not None
        assert view.customer.id == customer.id
        assert view.cart_service.get_customer().id == customer.id

    def test_recalling_a_walk_in_held_bill_stays_on_walk_in(self, view, db_session):
        product = _make_real_product(db_session)
        view.cart_service.add_item(product)

        held_id = SuspendedTransactionService.hold_bill(view.cart_service)
        view.cart_service.clear()

        with patch.object(sales_view_module.QMessageBox, "information"):
            with patch.object(SuspendedTransactionService, "get_latest_suspended") as mock_latest:
                mock_latest.return_value = MagicMock(id=held_id)
                view.recall_bill()

        assert view.customer is None
        assert view.cart_service.get_customer() is None
