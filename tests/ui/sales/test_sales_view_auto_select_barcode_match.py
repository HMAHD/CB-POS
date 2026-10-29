"""#641: Settings -> System -> "Auto-Select on Barcode Match" was saved but
never read. In the default ALL search mode a scan is a LIKE match, so a
barcode that is also part of a longer one (4791001 vs 47910012) found two
products and opened the multi-result search -- even though one product's
barcode matched the scan exactly. With the setting on, that exact match
goes straight to the quantity dialog; off, the search list opens as before.
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Product
from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def products(db_session):
    short = Product(name_en="AutoSel Short", barcode="7410641001", price=Decimal("100"))
    longer = Product(name_en="AutoSel Longer", barcode="74106410012", price=Decimal("200"))
    db_session.add_all([short, longer])
    db_session.commit()
    return short, longer


@pytest.fixture
def opened(monkeypatch):
    """Record which dialog the scan opened, without showing either."""
    calls: dict[str, object] = {}

    class _FakeQty:
        def __init__(self, product, parent=None, **_kw):
            calls["quantity"] = product

        def exec(self):
            return False

    class _FakeSearch:
        def __init__(self, parent=None):
            calls["search"] = True
            self.search_input = type("_In", (), {"setText": lambda *_a: None})()
            self.product_selected = type("_Sig", (), {"connect": lambda *_a: None})()

        def perform_search(self):
            pass

        def exec(self):
            return False

    monkeypatch.setattr("cbpos.ui.views.sales_view.QuantityDialog", _FakeQty)
    monkeypatch.setattr("cbpos.ui.views.sales_view.AdvancedSearchDialog", _FakeSearch)
    return calls


def _with_setting(monkeypatch, value: bool):
    real_get = ConfigService.get
    monkeypatch.setattr(
        ConfigService,
        "get",
        staticmethod(lambda key: value if key == "auto_select_barcode_match" else real_get(key)),
    )


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    v.current_search_mode = "ALL"
    yield v
    v.deleteLater()


def test_exact_barcode_goes_straight_to_quantity_when_on(view, products, opened, monkeypatch):
    _with_setting(monkeypatch, True)
    short, _ = products

    view.barcode_input.setText(short.barcode)
    view.process_barcode()

    assert "search" not in opened
    assert opened["quantity"].id == short.id


def test_exact_barcode_still_opens_the_search_list_when_off(view, products, opened, monkeypatch):
    _with_setting(monkeypatch, False)
    short, _ = products

    view.barcode_input.setText(short.barcode)
    view.process_barcode()

    assert opened.get("search") is True
    assert "quantity" not in opened


def test_partial_text_with_no_exact_barcode_opens_the_search_list(view, products, opened, monkeypatch):
    _with_setting(monkeypatch, True)

    view.barcode_input.setText("AutoSel")
    view.process_barcode()

    assert opened.get("search") is True
