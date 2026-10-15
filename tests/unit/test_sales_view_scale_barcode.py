"""Settings -> Hardware -> Weighing Scale ("Scale Barcode Prefix", "Decimal
Places") was saved but never read: ScaleService had no callers, so a
weighing-scale label (PP IIIII WWWWW C) scanned at the till was just an
unknown barcode. A scan now goes through the scale settings: prefix 20,
item code 00042, weight 01250 with 3 decimals -> product #42, 1.250 kg,
added straight to the cart.
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Product
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.scale_service import ScaleService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


def _ean13(body: str) -> str:
    odd = sum(int(d) for d in body[0::2])
    even = sum(int(d) for d in body[1::2])
    return body + str((10 - (odd + even * 3) % 10) % 10)


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def scale_settings(monkeypatch):
    values = {"scale_barcode_prefix": "21", "scale_decimal_places": 3}
    real_get = ConfigService.get
    monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key: values.get(key, real_get(key))))
    return values


@pytest.fixture
def rice(db_session):
    product = Product(name_en="Scale Rice", barcode="SCALE-RICE-641", price=Decimal("240"), is_weighted=True)
    db_session.add(product)
    db_session.commit()
    return product


@pytest.fixture
def warned(monkeypatch):
    """Record the 'not found' warning instead of blocking on a real message box."""
    calls: list[bool] = []
    monkeypatch.setattr("cbpos.ui.views.sales_view.QMessageBox.warning", lambda *a, **k: calls.append(True))
    return calls


@pytest.fixture
def view(qapp, db_session, monkeypatch, warned):
    v = SalesView()
    v.current_search_mode = "ALL"
    monkeypatch.setattr(v, "_confirm_age_restriction", lambda product: True)
    monkeypatch.setattr(
        "cbpos.ui.views.sales_view.QuantityDialog", lambda *a, **k: pytest.fail("scale label asked for a quantity")
    )
    yield v
    v.deleteLater()


def _scan(view, code):
    view.barcode_input.setText(code)
    view.process_barcode()


def test_scale_label_adds_the_weighed_item_with_its_weight(view, rice, scale_settings):
    _scan(view, _ean13(f"21{rice.id:05d}01250"))

    assert len(view.cart_service.items) == 1
    assert view.cart_service.items[0]["product"].id == rice.id
    assert view.cart_service.items[0]["qty"] == Decimal("1.250")
    assert view.barcode_input.text() == ""


def test_decimal_places_setting_is_used(view, rice, scale_settings):
    scale_settings["scale_decimal_places"] = 2

    _scan(view, _ean13(f"21{rice.id:05d}01250"))

    assert view.cart_service.items[0]["qty"] == Decimal("12.50")


def test_label_with_another_prefix_is_not_read_as_a_scale_label(view, rice, scale_settings, warned):
    _scan(view, _ean13(f"22{rice.id:05d}01250"))

    assert view.cart_service.items == []
    assert warned == [True]


def test_zero_decimal_places_means_whole_units():
    assert ScaleService.parse_barcode(_ean13("200004200007"), prefix="20", decimal_places=0)["qty"] == Decimal("7")
