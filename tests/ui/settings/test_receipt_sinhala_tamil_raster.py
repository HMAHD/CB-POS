"""
#625: Sinhala/Tamil receipt lines print as images, not "????".

ESC/POS printers have no Sinhala/Tamil code page; python-escpos sends each
such character as "?". The driver now draws those lines (only those) with
Qt and the bundled Noto fonts and prints them as an image. English lines
stay text. Real glyph output still has to be checked on a real printer --
here the printer is a mock.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cbpos.core.models import Product, Sale, SaleItem, SalePayment
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver, PrintWorker
from cbpos.infrastructure.hardware.text_raster import needs_raster, render_text_line

pytestmark = pytest.mark.usefixtures("qapp")

SINHALA = "මුළු එකතුව"
TAMIL = "மொத்த தொகை"


def _black_pixels(img) -> int:
    return img.convert("L").histogram()[0]


class TestNeedsRaster:
    @pytest.mark.parametrize("text", [SINHALA, TAMIL, f"{SINHALA}: Rs. 100.00"])
    def test_sinhala_and_tamil_need_raster(self, text):
        assert needs_raster(text)

    @pytest.mark.parametrize("text", ["TOTAL AMOUNT:", "Rs. 1,250.00", "Café", ""])
    def test_latin_text_stays_text(self, text):
        assert not needs_raster(text)


class TestRenderTextLine:
    @pytest.mark.parametrize(("paper", "width"), [("80mm", 576), ("58mm", 384)])
    def test_image_fills_paper_width_and_has_ink(self, paper, width):
        img = render_text_line({"type": "text", "val": SINHALA, "align": "center"}, paper)

        assert img.mode == "1"
        assert img.width == width
        assert _black_pixels(img) > 50

    def test_two_column_row_puts_amount_on_the_right(self):
        img = render_text_line({"type": "text", "val": "x", "left_val": SINHALA, "right_val": "Rs. 100.00"})

        right_half = img.crop((img.width * 3 // 4, 0, img.width, img.height))
        middle = img.crop((img.width * 2 // 5, 0, img.width * 3 // 5, img.height))
        assert _black_pixels(right_half) > 0
        assert _black_pixels(middle) == 0

    def test_very_long_line_is_shrunk_not_cut(self):
        img = render_text_line({"type": "text", "val": SINHALA * 6, "align": "left"})
        assert img.width == 576  # still paper width, text drawn smaller


class TestDriverPrintsSinhalaAsImage:
    def _driver(self) -> ESCPOSDriver:
        driver = ESCPOSDriver()
        driver.printer = MagicMock()
        return driver

    def test_sinhala_line_goes_out_as_image(self):
        driver = self._driver()

        driver.print_commands([{"type": "text", "val": SINHALA, "align": "center"}])

        driver.printer.image.assert_called_once()
        driver.printer.text.assert_not_called()

    def test_english_line_stays_text(self):
        driver = self._driver()

        driver.print_commands([{"type": "text", "val": "TOTAL AMOUNT:", "align": "left"}])

        driver.printer.text.assert_called_once_with("TOTAL AMOUNT:\n")
        driver.printer.image.assert_not_called()

    def test_sinhala_receipt_sends_no_sinhala_as_text(self, monkeypatch):
        settings = {**ConfigService.DEFAULTS, "receipt_language": "si", "receipt_header": ""}
        monkeypatch.setattr(ConfigService, "get", classmethod(lambda cls, k: settings.get(k)))
        sale = Sale(
            id=1,
            document_number="INV-1",
            date=datetime(2026, 10, 7, 10, 0),
            total_amount=Decimal("100.00"),
            tax_vat=Decimal("0"),
            tax_sscl=Decimal("0"),
            net_revenue=Decimal("100.00"),
        )
        sale.items = [
            SaleItem(
                product=Product(name_en="Soap"),
                qty=Decimal("1"),
                unit_price=Decimal("100.00"),
                subtotal=Decimal("100.00"),
            )
        ]
        sale.payments = [SalePayment(payment_method="CASH", amount=Decimal("100.00"))]
        commands = ReceiptBuilder.build_receipt(sale)
        assert any(needs_raster(c.get("val", "")) for c in commands)  # really a Sinhala receipt
        driver = self._driver()

        driver.print_commands(commands)

        sent_as_text = "".join(call.args[0] for call in driver.printer.text.call_args_list)
        assert not needs_raster(sent_as_text)
        assert driver.printer.image.call_count == sum(1 for c in commands if needs_raster(c.get("val", "")))


class _MockConnectDriver(ESCPOSDriver):
    def connect(self) -> bool:
        self.printer = MagicMock()
        return True


def test_rendering_works_on_the_print_worker_thread(qtbot):
    driver = _MockConnectDriver()
    worker = PrintWorker(printer=driver)
    try:
        with qtbot.waitSignal(worker.job_completed, timeout=5000):
            worker.add_job("print_receipt", [{"type": "text", "val": TAMIL, "align": "center"}])
    finally:
        worker.stop()
        worker.wait(5000)

    (img,), _ = driver.printer.image.call_args
    assert _black_pixels(img) > 50
