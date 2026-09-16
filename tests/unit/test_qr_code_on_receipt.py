"""
#328: 'code': 'QR' was documented in base_receipt_builder.py's own
schema comment, and show_qr_on_receipt/receipt_qr_content already had
config defaults, but a full-repo grep showed neither was ever read,
never emitted by any builder, never had a Display-tab toggle, and the
printer driver's barcode branch only ever called printer.barcode()
(a 1D-symbology call that can't render a QR at all). Finished what was
started: a toggle + content field, real emission, a real printer.qr()
call, and a real scannable preview.
"""

from unittest.mock import MagicMock

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder
from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver
from cbpos.ui.views.settings_pages import ReceiptPage
from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data):
        self._data.update(data)


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore(dict(ConfigService.DEFAULTS))
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(ConfigService, "set", store.set)
    monkeypatch.setattr(ConfigService, "update_all", store.update_all)
    return store


@pytest.fixture
def page(qapp, config_store):
    p = ReceiptPage()
    yield p
    p._refresh_timer.stop()
    p.deleteLater()


def _dummy_sale():
    from datetime import datetime
    from decimal import Decimal

    from cbpos.core.models import Product, Sale, SaleItem

    sale = Sale(
        id=1,
        document_number="INV-TEST-1",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        tax_vat=Decimal("0"),
        tax_sscl=Decimal("0"),
        net_revenue=Decimal("100.00"),
    )
    product = Product(name_en="Widget")
    sale.items = [
        SaleItem(
            product=product,
            qty=Decimal("1"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("100.00"),
        )
    ]
    sale.payments = []
    return sale


class TestReceiptBuilderEmitsQrWhenConfigured:
    def test_qr_command_emitted_when_enabled_with_content(self, config_store):
        config_store.set("show_qr_on_receipt", True)
        config_store.set("receipt_qr_content", "https://wa.me/94771234567")

        commands = SalesReceiptBuilder.build_receipt(_dummy_sale())

        qr_commands = [c for c in commands if c.get("type") == "barcode" and c.get("code") == "QR"]
        assert len(qr_commands) == 1
        assert qr_commands[0]["val"] == "https://wa.me/94771234567"

    def test_no_qr_command_when_disabled(self, config_store):
        config_store.set("show_qr_on_receipt", False)
        config_store.set("receipt_qr_content", "https://wa.me/94771234567")

        commands = SalesReceiptBuilder.build_receipt(_dummy_sale())

        assert not [c for c in commands if c.get("code") == "QR"]

    def test_no_qr_command_when_enabled_but_content_is_empty(self, config_store):
        config_store.set("show_qr_on_receipt", True)
        config_store.set("receipt_qr_content", "")

        commands = SalesReceiptBuilder.build_receipt(_dummy_sale())

        assert not [c for c in commands if c.get("code") == "QR"]


class TestPrinterDriverRoutesQrToItsOwnCommand:
    def test_qr_barcode_calls_printer_qr_not_printer_barcode(self):
        driver = ESCPOSDriver()
        driver.printer = MagicMock()

        driver.print_commands([{"type": "barcode", "val": "https://example.com", "code": "QR", "align": "center"}])

        driver.printer.qr.assert_called_once()
        driver.printer.barcode.assert_not_called()
        assert driver.printer.qr.call_args[0][0] == "https://example.com"

    def test_1d_barcode_still_calls_printer_barcode(self):
        driver = ESCPOSDriver()
        driver.printer = MagicMock()

        driver.print_commands([{"type": "barcode", "val": "INV-1", "code": "CODE39", "align": "center"}])

        driver.printer.barcode.assert_called_once()
        driver.printer.qr.assert_not_called()


class TestPreviewRendersARealScannableQr:
    def test_qr_command_embeds_a_data_uri_image(self):
        widget = ReceiptPreviewWidget()
        widget.set_commands([{"type": "barcode", "val": "https://example.com", "code": "QR", "align": "center"}])
        html = widget._browser.toHtml()
        assert "data:image/png;base64," in html

    def test_qr_preview_has_no_not_scannable_caveat(self):
        widget = ReceiptPreviewWidget()
        widget.set_commands([{"type": "barcode", "val": "https://example.com", "code": "QR", "align": "center"}])
        html = widget._browser.toHtml()
        assert "preview only" not in html.lower()


class TestReceiptPageHasAQrToggleAndContentField:
    def test_toggle_and_field_exist(self, page):
        assert page.chk_show_qr is not None
        assert page.txt_qr_content is not None

    def test_save_round_trips_qr_settings(self, page):
        page.chk_show_qr.setChecked(True)
        page.txt_qr_content.setText("https://wa.me/94771234567")

        saved = page.save()

        assert saved["show_qr_on_receipt"] is True
        assert saved["receipt_qr_content"] == "https://wa.me/94771234567"

    def test_load_restores_qr_settings(self, page):
        page.load({"show_qr_on_receipt": True, "receipt_qr_content": "https://ceybyte.com"})

        assert page.chk_show_qr.isChecked() is True
        assert page.txt_qr_content.text() == "https://ceybyte.com"
