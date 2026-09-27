"""
#488: process_barcode() only tried a loyalty-card lookup when the scanned
text happened to start with "L-" or was exactly 12 digits -- a guess the
code's own comment admitted ("Assuming L- prefix for now as per request").
But Customer.loyalty_card_code is free text set in CustomerEditor with no
fixed prefix or length, so any card code that didn't happen to match that
shape was never looked up at all, silently falling through to a failed
product search instead of selecting the customer.
"""

import pytest

from cbpos.core.models import Customer
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


class TestLoyaltyCardScanSelectsCustomer:
    def test_arbitrary_format_card_code_selects_the_customer(self, view, db_session):
        customer = Customer(
            name="Loyalty Test Customer",
            phone="0711234567",
            loyalty_card_code="MYCARD-not-L-prefixed-or-12-digits",
            loyalty_points=15,
        )
        db_session.add(customer)
        db_session.commit()

        view.barcode_input.setText(customer.loyalty_card_code)
        view.process_barcode()

        assert view.customer is not None
        assert view.customer.id == customer.id
        assert view.barcode_input.text() == ""

    def test_unrelated_barcode_falls_through_to_product_search(self, view, db_session, monkeypatch):
        Customer(name="Some Other Customer", loyalty_card_code="SOME-OTHER-CARD")
        warned = []
        monkeypatch.setattr(
            "cbpos.ui.views.sales_view.QMessageBox.warning",
            lambda *a, **k: warned.append(True),
        )

        view.barcode_input.setText("NO-SUCH-CARD-OR-PRODUCT")
        view.process_barcode()

        assert view.customer is None
        assert warned == [True]
