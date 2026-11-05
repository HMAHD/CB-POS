"""#733: the production peripherals adapter keeps the shop's receipt and drawer policy.

The shared PrintWorker is a stub that records the jobs queued on it, in
order; ConfigService is backed by a dict. No printer is touched.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from cbpos.core.interfaces.transaction_peripherals import RefundCompleted, SaleCompleted
from cbpos.core.models import Product, Sale, SaleItem, SalePayment
from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.infrastructure.hardware.print_worker_peripherals import PrintWorkerPeripherals


class _StubWorker:
    """Stands in for the shared PrintWorker: records (job_type, data) in queue order."""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, Any]] = []

    def add_job(self, job_type: str, data: Any = None) -> None:
        self.jobs.append((job_type, data))

    def job_types(self) -> list[str]:
        return [job_type for job_type, _ in self.jobs]


@pytest.fixture
def settings(monkeypatch):
    values = dict(ConfigService.DEFAULTS)
    values.update(receipt_language="en", auto_print_receipt=True, show_receipt_dialog=False, receipt_copies=1)
    monkeypatch.setattr(ConfigService, "get", lambda key, *_a: values.get(key))
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(values))
    return values


@pytest.fixture
def worker():
    stub = _StubWorker()
    with patch.object(PrintWorker, "instance", return_value=stub):
        yield stub


def _sale(*methods: str) -> Sale:
    sale = Sale(
        id=7,
        document_number="INV-2026-00007",
        date=datetime(2026, 10, 7, 9, 30),
        total_amount=Decimal("236.00"),
        tax_vat=Decimal("0"),
        tax_sscl=Decimal("0"),
        net_revenue=Decimal("236.00"),
        payment_method=methods[0] if len(methods) == 1 else "SPLIT",
        status="COMPLETED",
    )
    sale.items = [
        SaleItem(
            product=Product(name_en="Dhal 1kg"),
            qty=Decimal("2"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("236.00"),
        )
    ]
    sale.payments = [SalePayment(payment_method=m, amount=Decimal("236.00")) for m in methods]
    sale.customer = None
    return sale


def _sold(*methods: str) -> SaleCompleted:
    return SaleCompleted(_sale(*methods), tuple(methods))


def test_a_sale_prints_the_receipt_then_opens_the_drawer(settings, worker):
    PrintWorkerPeripherals().sale_completed(_sold("CASH"))

    assert worker.job_types() == ["print_receipt", "kick_drawer"]


def test_with_the_receipt_dialog_on_the_dialog_prints_but_the_drawer_still_opens(settings, worker):
    settings["show_receipt_dialog"] = True

    PrintWorkerPeripherals().sale_completed(_sold("CASH"))

    assert worker.jobs == [("kick_drawer", {"manual": False, "method_kinds": ["CASH"]})]


def test_with_auto_print_off_only_the_drawer_opens(settings, worker):
    settings["auto_print_receipt"] = False

    PrintWorkerPeripherals().sale_completed(_sold("CASH"))

    assert worker.job_types() == ["kick_drawer"]


def test_the_drawer_kick_carries_every_payment_method_for_drawer_on_cash_only(settings, worker):
    """The worker keeps the drawer shut for a sale with no cash when drawer_on_cash_only is on."""
    PrintWorkerPeripherals().sale_completed(_sold("CARD", "BANK"))

    assert worker.jobs[-1] == ("kick_drawer", {"manual": False, "method_kinds": ["CARD", "OTHER"]})


def test_a_receipt_that_fails_to_build_still_opens_the_drawer(settings, worker, caplog):
    with patch(
        "cbpos.infrastructure.hardware.print_worker_peripherals.PrinterService.print_transaction",
        side_effect=ValueError("bad logo"),
    ):
        PrintWorkerPeripherals().sale_completed(_sold("CASH"))

    assert worker.jobs == [("kick_drawer", {"manual": False, "method_kinds": ["CASH"]})]
    assert "bad logo" in caplog.text


def test_a_refund_prints_its_voucher(settings, worker):
    voucher = [{"type": "text", "val": "REFUND"}, {"type": "cut", "partial": True}]

    PrintWorkerPeripherals().refund_completed(RefundCompleted(_sale("REFUND"), voucher))

    assert worker.jobs == [("print_receipt", voucher)]
