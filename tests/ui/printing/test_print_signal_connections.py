"""
Regression tests for a bug introduced as a side effect of making
PrintWorker a shared singleton (see test_print_worker.py): any call site
that does `worker.error_occurred.connect(self._on_print_error)` without
guarding against reconnection now accumulates one connection per call,
since the same underlying QObject persists across calls instead of being
garbage collected each time.

ReceiptOptionsDialog.print_thermal() is one such call site -- its own
Retry button (in _on_print_error) calls print_thermal() again, so each
retry added another duplicate connection; a later failure would then pop
up as one warning dialog per accumulated connection instead of one.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, User
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.receipt_options_dialog import ReceiptOptionsDialog

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"psc_test_{suffix}")
    role = Role(name=f"PscRole_{suffix}", permissions=[permission])
    user = User(username=f"psc_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(name_en=f"PscProduct_{_counter}", price=100.0, stock_qty=10.0, barcode=f"PSC{_counter:04d}")
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def sale(db_session, test_user, test_product):
    global _counter
    _counter += 1
    sale = Sale(
        document_number=f"REC-PSC-{_counter}",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=200,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.flush()
    db_session.add(
        SaleItem(
            sale_id=sale.id,
            product_id=test_product.id,
            qty=2.0,
            unit_price=100.0,
            original_price=100.0,
            subtotal=200.0,
        )
    )
    db_session.commit()
    return sale


@pytest.fixture
def dialog(qapp, sale):
    dlg = ReceiptOptionsDialog(sale)
    yield dlg
    PrintWorker.shutdown()
    dlg.deleteLater()


class TestNoDuplicatePrintSignalConnections:
    def test_calling_print_thermal_repeatedly_connects_only_once(self, dialog):
        # Patch before the first call so every print_thermal() call --
        # including the one made by _on_print_error's own Retry button --
        # connects to this same tracked callable throughout. add_job()
        # itself is mocked out so no real background thread ever starts
        # (this test is only about the connect/disconnect guard, not
        # actual print execution or hardware access).
        error_calls = []
        dialog._on_print_error = lambda message: error_calls.append(message)

        with patch.object(PrintWorker, "add_job", return_value="job_thermal_1"):
            for _ in range(5):  # simulates 5 retries
                dialog.print_thermal()

        PrintWorker.instance().job_result.emit("job_thermal_1", False, "Printer not available.")

        assert error_calls == ["Printer not available."]

    def test_calling_print_thermal_repeatedly_only_finishes_once(self, dialog):
        finished_calls = []
        dialog._on_print_finished = lambda: finished_calls.append(True)

        with patch.object(PrintWorker, "add_job", return_value="job_thermal_2"):
            for _ in range(5):
                dialog.print_thermal()

        PrintWorker.instance().job_result.emit("job_thermal_2", True, "")

        assert finished_calls == [True]
