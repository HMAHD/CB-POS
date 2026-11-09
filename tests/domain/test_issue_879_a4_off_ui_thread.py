"""Tests for #879: A4 tax invoice PDF generation off the UI thread."""

import contextlib
import threading
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cbpos.core.database import Database
from cbpos.core.interfaces.transaction_peripherals import SaleCompleted
from cbpos.core.models import Customer, Product, Sale, SaleItem, SalePayment
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.printer_service import PrinterService
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.infrastructure.hardware.print_worker_peripherals import PrintWorkerPeripherals


@pytest.fixture
def mock_sale():
    sale = Sale(
        id=879,
        document_number="INV-2026-000879",
        date=datetime(2026, 10, 20, 10, 0),
        total_amount=Decimal("5000.00"),
        tax_vat=Decimal("762.71"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("4237.29"),
        payment_method="CASH",
        status="COMPLETED",
        customer=Customer(name="B2B Construction Ltd", vat_number="123456789-7000"),
    )
    sale.items = [
        SaleItem(
            product=Product(barcode="BAR-879", name_en="Steel Rod 12mm", price=Decimal("5000.00")),
            qty=Decimal("1"),
            unit_price=Decimal("5000.00"),
            original_price=Decimal("5000.00"),
            subtotal=Decimal("5000.00"),
        )
    ]
    sale.payments = [SalePayment(payment_method="CASH", amount=Decimal("5000.00"))]
    return sale


def test_issue_879_sale_completed_does_not_build_pdf_on_calling_thread(qtbot, mock_sale, monkeypatch):
    """sale_completed for a VAT-registered customer must not generate the PDF on the caller's thread."""
    threads_used = []

    def mock_generate_pdf(sale, path):
        threads_used.append(threading.current_thread())

    monkeypatch.setattr(InvoiceService, "generate_pdf", mock_generate_pdf)
    monkeypatch.setattr(PrinterService, "_send_pdf_to_printer", lambda path, printer: None)
    monkeypatch.setattr(
        ConfigService, "get", lambda k, *_a: "Office A4" if k == "a4_printer_name" else ConfigService.DEFAULTS.get(k)
    )

    mock_session = MagicMock()
    mock_session.query.return_value.options.return_value.filter.return_value.first.return_value = mock_sale
    monkeypatch.setattr(Database, "get_session", lambda self: contextlib.nullcontext(mock_session))

    mock_printer = MagicMock()
    mock_printer.connect.return_value = True

    worker = PrintWorker(printer=mock_printer)
    monkeypatch.setattr(PrintWorker, "instance", classmethod(lambda cls: worker))

    calling_thread = threading.current_thread()
    event = SaleCompleted(mock_sale, ("CASH",))

    # sale_completed must return immediately without having called generate_pdf synchronously
    PrintWorkerPeripherals().sale_completed(event)
    assert len(threads_used) == 0, "generate_pdf should not be called synchronously inside sale_completed"

    # Wait for the worker thread to process jobs
    qtbot.waitUntil(lambda: len(threads_used) == 1, timeout=5000)

    assert threads_used[0] != calling_thread
    assert threads_used[0] != threading.main_thread()

    worker.stop()
    worker.wait(5000)


def test_issue_879_a4_job_failure_reports_error(qtbot, mock_sale, monkeypatch):
    """When A4 invoice generation fails, job_result and error_occurred emit the failure."""
    monkeypatch.setattr(InvoiceService, "generate_pdf", MagicMock(side_effect=RuntimeError("Disk full")))
    monkeypatch.setattr(
        ConfigService, "get", lambda k, *_a: "Office A4" if k == "a4_printer_name" else ConfigService.DEFAULTS.get(k)
    )

    mock_session = MagicMock()
    mock_session.query.return_value.options.return_value.filter.return_value.first.return_value = mock_sale
    monkeypatch.setattr(Database, "get_session", lambda self: contextlib.nullcontext(mock_session))

    mock_printer = MagicMock()
    mock_printer.connect.return_value = True

    worker = PrintWorker(printer=mock_printer)
    results = []
    errors = []
    worker.job_result.connect(lambda jid, ok, msg: results.append((jid, ok, msg)))
    worker.error_occurred.connect(lambda msg: errors.append(msg))

    job_id = worker.add_job("a4_invoice", mock_sale.id)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)

    expected_msg = _t("printer.a4_invoice_failed", document=mock_sale.document_number, error="Disk full")
    assert results == [(job_id, False, expected_msg)]
    assert errors == [expected_msg]

    worker.stop()
    worker.wait(5000)
