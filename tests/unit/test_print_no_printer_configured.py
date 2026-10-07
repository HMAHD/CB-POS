"""
#623: with no receipt printer configured (printer_type NONE),
PrintWorker._resolve_printer() used to hand back NullPrinter, whose
connect() always succeeds and whose every call is a no-op. Each job then
emitted job_completed, so every screen that waits for it told the cashier
"Receipt sent to printer" while nothing came out -- and the auto-print
after a sale failed silently.

The worker must report a missing printer as an error, the reprint screens
must therefore never show success.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, User
from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import NullPrinter, PrintWorker
from cbpos.ui.views.document_view import DocumentBrowserView

_counter = 0


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


def _use_printer_type(monkeypatch: pytest.MonkeyPatch, printer_type: str) -> None:
    """Force printer_type in settings without touching the rest of them."""
    real_get_all = ConfigService.get_all
    monkeypatch.setattr(
        ConfigService, "get_all", classmethod(lambda cls: {**real_get_all(), "printer_type": printer_type})
    )


@pytest.fixture
def no_printer(monkeypatch):
    _use_printer_type(monkeypatch, "NONE")


@pytest.fixture
def sale_doc(db_session) -> dict:
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"npc_test_{suffix}")
    role = Role(name=f"NpcRole_{suffix}", permissions=[permission])
    user = User(username=f"npc_user_{suffix}", pin_hash="hash", role=role)
    product = Product(name_en=f"NpcProduct_{suffix}", price=100.0, stock_qty=10.0, barcode=f"NPC{_counter:04d}")
    db_session.add_all([permission, role, user, product])
    db_session.flush()
    sale = Sale(
        document_number=f"REC-NPC-{suffix}",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        user_id=user.id,
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
            sale_id=sale.id, product_id=product.id, qty=2.0, unit_price=100.0, original_price=100.0, subtotal=200.0
        )
    )
    db_session.commit()
    doc = {"type": "sale", "id": sale.id, "document_number": sale.document_number}
    # Drop it from the shared test session's identity map so the reprint's
    # own query really eager-loads items, as it does in the app.
    db_session.expunge_all()
    return doc


class TestWorkerReportsMissingPrinter:
    def test_receipt_job_with_no_printer_errors_instead_of_completing(self, qtbot, no_printer):
        worker = PrintWorker.instance()
        completed: list[bool] = []
        worker.job_completed.connect(lambda: completed.append(True))

        with qtbot.waitSignal(worker.error_occurred, timeout=5000) as blocker:
            worker.add_job("print_receipt", [{"type": "text", "val": "x"}])

        assert blocker.args == [_t("printer.not_configured")]
        qtbot.wait(200)  # give a wrongly-emitted job_completed time to arrive
        assert completed == []

    def test_drawer_job_with_no_printer_is_silent(self, qtbot, no_printer):
        """No printer means no drawer: every cash sale queues a kick, and
        it must neither claim success nor raise a "not set up" error."""
        worker = PrintWorker.instance()
        signals: list[str] = []
        worker.job_completed.connect(lambda: signals.append("completed"))
        worker.error_occurred.connect(lambda msg: signals.append(msg))

        worker.add_job("kick_drawer", ["CASH"])
        # A receipt job queued after it proves the drawer job was processed.
        with qtbot.waitSignal(worker.error_occurred, timeout=5000):
            worker.add_job("print_receipt", [])
        qtbot.wait(200)

        assert signals == [_t("printer.not_configured")]

    def test_injected_null_printer_still_completes(self, qtbot, no_printer):
        """NullPrinter stays usable when passed in explicitly (tests/dev)."""
        worker = PrintWorker(printer=NullPrinter())
        try:
            with qtbot.waitSignal(worker.job_completed, timeout=5000):
                worker.add_job("print_receipt", [])
        finally:
            worker.stop()
            worker.wait(5000)


class TestReprintWithNoPrinter:
    def test_document_browser_reprint_shows_error_not_success(self, qtbot, no_printer, sale_doc):
        view = DocumentBrowserView()
        view.current_doc = sale_doc
        with patch("cbpos.ui.views.document_view.QMessageBox") as mock_box:
            view.reprint_document()
            qtbot.waitUntil(lambda: mock_box.critical.called or mock_box.information.called, timeout=5000)
            qtbot.wait(200)
            mock_box.information.assert_not_called()
            mock_box.critical.assert_called_once()
        view.deleteLater()


class TestHardwareTestDrawerStillReportsNotConfigured:
    def test_test_cash_drawer_with_no_printer_fails(self, no_printer):
        from cbpos.core.services.hardware_test_service import HardwareTestService

        ok, message = HardwareTestService.test_cash_drawer()
        assert ok is False
        assert "No printer configured" in message
