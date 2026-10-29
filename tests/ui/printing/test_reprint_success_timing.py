"""
Tests that Sale History and Receipt Reprint's reprint actions only report
success once the print job actually completes, and show a plain,
non-technical message on failure instead of a raw exception string.

PrintWorker.add_job() only queues a job -- the print itself happens later,
asynchronously, on the worker thread, and is only reported via the
error_occurred/job_completed signals. Both dialogs used to show
QMessageBox.information("...success...") immediately after add_job(),
unconditionally, so a shop owner with no printer configured was told the
reprint worked when nothing had actually printed, and the only real
feedback (a WARNING log line) never reached them.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, User
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.receipt_reprint_dialog import ReceiptReprintDialog
from cbpos.ui.dialogs.sale_history_dialog import SaleHistoryDialog

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"rst_test_{suffix}")
    role = Role(name=f"RstRole_{suffix}", permissions=[permission])
    user = User(username=f"rst_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(name_en=f"RstProduct_{_counter}", price=100.0, stock_qty=10.0, barcode=f"RST{_counter:04d}")
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def sale(db_session, test_user, test_product):
    global _counter
    _counter += 1
    sale = Sale(
        document_number=f"REC-RST-{_counter}",
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


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


class TestSaleHistoryDialogReprintTiming:
    def test_no_success_message_before_job_completes(self, qapp, sale):
        dlg = SaleHistoryDialog()
        dlg._selected_sale = sale

        with (
            patch.object(PrintWorker, "add_job"),
            patch("cbpos.ui.dialogs.sale_history_dialog.QMessageBox") as mock_box,
        ):
            dlg._reprint_receipt()
            mock_box.information.assert_not_called()
            mock_box.critical.assert_not_called()

        dlg.deleteLater()

    def test_success_message_shown_once_job_completes(self, qapp, sale):
        dlg = SaleHistoryDialog()
        dlg._selected_sale = sale

        with (
            patch.object(PrintWorker, "add_job"),
            patch("cbpos.ui.dialogs.sale_history_dialog.QMessageBox") as mock_box,
        ):
            dlg._reprint_receipt()
            PrintWorker.instance().job_completed.emit()
            mock_box.information.assert_called_once()
            mock_box.critical.assert_not_called()

        dlg.deleteLater()

    def test_failure_shows_plain_message_not_raw_exception(self, qapp, sale):
        dlg = SaleHistoryDialog()
        dlg._selected_sale = sale

        with (
            patch.object(PrintWorker, "add_job"),
            patch("cbpos.ui.dialogs.sale_history_dialog.QMessageBox") as mock_box,
        ):
            dlg._reprint_receipt()
            PrintWorker.instance().error_occurred.emit("Printer not available.")

            mock_box.critical.assert_called_once()
            shown_text = mock_box.critical.call_args[0][2]
            assert "Printer not available." not in shown_text
            assert "DetachedInstanceError" not in shown_text

        dlg.deleteLater()


class TestReceiptReprintDialogTiming:
    def test_no_success_message_before_job_completes(self, qapp, sale):
        dlg = ReceiptReprintDialog()
        dlg.results = [sale]

        with (
            patch.object(PrintWorker, "add_job"),
            patch("cbpos.ui.dialogs.receipt_reprint_dialog.QMessageBox") as mock_box,
        ):
            dlg.results_table.insertRow(0)
            dlg.results_table.selectRow(0)
            dlg.reprint_selected()
            mock_box.information.assert_not_called()

        dlg.deleteLater()

    def test_success_message_shown_once_job_completes(self, qapp, sale):
        dlg = ReceiptReprintDialog()
        dlg.results = [sale]

        with (
            patch.object(PrintWorker, "add_job"),
            patch("cbpos.ui.dialogs.receipt_reprint_dialog.QMessageBox") as mock_box,
        ):
            dlg.results_table.insertRow(0)
            dlg.results_table.selectRow(0)
            dlg.reprint_selected()
            PrintWorker.instance().job_completed.emit()
            mock_box.information.assert_called_once()

        dlg.deleteLater()
