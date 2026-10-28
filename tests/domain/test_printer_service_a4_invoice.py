"""#740: a failed A4 Tax Invoice reaches the cashier, not only the log.

The A4 invoice for a VAT-registered customer is printed after the sale,
with no dialog of its own. Its failures used to be logged and dropped, so
the buyer silently got no tax invoice. They now go out on the print
worker's ``error_occurred`` -- the path the Sales screen already shows
print failures from.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.models import Customer, Product, Sale, SaleItem
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.printer_service import PrinterService
from cbpos.i18n import translate_in
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker


@pytest.fixture
def settings(monkeypatch):
    values = dict(ConfigService.DEFAULTS)
    values.update(receipt_language="en", a4_printer_name="Office A4")
    monkeypatch.setattr(ConfigService, "get", lambda key, *_a: values.get(key))
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(values))
    return values


@pytest.fixture
def worker():
    mock = MagicMock()
    with patch.object(PrintWorker, "instance", return_value=mock):
        yield mock


def _b2b_sale() -> Sale:
    sale = Sale(
        id=77,
        document_number="REC-000077",
        date=datetime(2026, 10, 15, 9, 0),
        total_amount=Decimal("2360.00"),
        tax_vat=Decimal("360.00"),
        tax_sscl=Decimal("25.00"),
        net_revenue=Decimal("1975.00"),
        payment_method="CASH",
        customer=Customer(name="Lanka Builders", vat_number="114567890-7000"),
    )
    sale.items = [
        SaleItem(
            product=Product(name_en="Cement 50kg", price=Decimal("2360")),
            qty=Decimal("1"),
            unit_price=Decimal("2360.00"),
            original_price=Decimal("2360.00"),
            subtotal=Decimal("2360.00"),
        )
    ]
    return sale


def _reported(worker: MagicMock) -> list[str]:
    return [c.args[0] for c in worker.error_occurred.emit.call_args_list]


@pytest.mark.usefixtures("settings")
class TestA4InvoiceAutoPrint:
    def test_builds_the_invoice_and_sends_it_to_the_a4_printer(self, worker):
        with patch.object(PrinterService, "_send_pdf_to_printer") as send:
            PrinterService.maybe_print_b2b_invoice(_b2b_sale())

        ((pdf_path, printer),) = [c.args for c in send.call_args_list]
        assert printer == "Office A4"
        with open(pdf_path, "rb") as f:
            assert f.read(5) == b"%PDF-"
        assert _reported(worker) == []

    def test_invoice_that_fails_to_build_is_reported_to_the_cashier(self, worker):
        with (
            patch.object(InvoiceService, "generate_pdf", side_effect=RuntimeError("disk full")),
            patch.object(PrinterService, "_send_pdf_to_printer") as send,
        ):
            PrinterService.maybe_print_b2b_invoice(_b2b_sale())

        send.assert_not_called()
        expected = translate_in("en", "printer.a4_invoice_failed", document="REC-000077", error="disk full")
        assert _reported(worker) == [expected]

    def test_invoice_that_fails_to_reach_the_printer_is_reported(self, worker):
        with patch("subprocess.Popen", side_effect=FileNotFoundError("powershell")):
            PrinterService.maybe_print_b2b_invoice(_b2b_sale())

        (message,) = _reported(worker)
        assert "REC-000077" in message

    def test_no_a4_printer_set_up_is_not_an_error(self, settings, worker):
        settings["a4_printer_name"] = None

        with patch.object(InvoiceService, "generate_pdf") as build:
            PrinterService.maybe_print_b2b_invoice(_b2b_sale())

        build.assert_not_called()
        assert _reported(worker) == []
