"""
Same false-success bug as test_reprint_success_timing.py (#244/#246),
found in 4 more places by grepping every PrintWorker.instance() call site:
customer_statement_dialog.py, label_print_dialog.py, document_view.py
(two occurrences), and history_view.py. All showed a success QMessageBox
immediately after add_job() -- before the async job actually ran -- so a
shop owner with no printer configured was told printing worked when
nothing had actually printed.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Customer, Permission, Product, Role, Sale, SaleItem, User
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.customer_statement_dialog import CustomerStatementDialog
from cbpos.ui.dialogs.label_print_dialog import LabelPrintDialog
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.history_view import HistoryView

_counter = 0


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    perm_reprint = db_session.query(Permission).filter_by(code=Permissions.SALES_REPRINT).first()
    if not perm_reprint:
        perm_reprint = Permission(code=Permissions.SALES_REPRINT)
        db_session.add(perm_reprint)
    permission = Permission(code=f"ptr_test_{suffix}")
    role = Role(name=f"PtrRole_{suffix}", permissions=[permission, perm_reprint])
    user = User(username=f"ptr_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user):
        yield user


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(name_en=f"PtrProduct_{_counter}", price=100.0, stock_qty=10.0, barcode=f"PTR{_counter:04d}")
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def test_customer(db_session):
    global _counter
    _counter += 1
    customer = Customer(name=f"PtrCustomer_{_counter}")
    db_session.add(customer)
    db_session.flush()
    return customer


@pytest.fixture
def sale(db_session, test_user, test_product):
    global _counter
    _counter += 1
    sale = Sale(
        document_number=f"REC-PTR-{_counter}",
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


class TestCustomerStatementDialogTiming:
    def test_no_success_before_job_completes(self, qapp, test_customer):
        dlg = CustomerStatementDialog(test_customer)
        with (
            patch.object(PrintWorker, "add_job", return_value="job_stmt_1"),
            patch("cbpos.ui.dialogs.customer_statement_dialog.QMessageBox") as mock_box,
        ):
            dlg._print_thermal()
            mock_box.information.assert_not_called()
        dlg.deleteLater()

    def test_success_shown_once_job_completes(self, qapp, test_customer):
        dlg = CustomerStatementDialog(test_customer)
        with (
            patch.object(PrintWorker, "add_job", return_value="job_stmt_1"),
            patch("cbpos.ui.dialogs.customer_statement_dialog.QMessageBox") as mock_box,
        ):
            dlg._print_thermal()
            PrintWorker.instance().job_result.emit("job_stmt_1", True, "")
            mock_box.information.assert_called_once()
        dlg.deleteLater()


class TestLabelPrintDialogTiming:
    def test_no_success_before_job_completes(self, qapp, test_product):
        dlg = LabelPrintDialog()
        dlg.label_items = [{"product": test_product, "quantity": 2}]
        with (
            patch.object(PrintWorker, "add_job", return_value="job_label_1"),
            patch("cbpos.ui.dialogs.label_print_dialog.QMessageBox") as mock_box,
        ):
            dlg._print_labels()
            mock_box.information.assert_not_called()
        dlg.deleteLater()

    def test_success_shown_once_job_completes(self, qapp, test_product):
        dlg = LabelPrintDialog()
        dlg.label_items = [{"product": test_product, "quantity": 2}]
        with (
            patch.object(PrintWorker, "add_job", return_value="job_label_1"),
            patch("cbpos.ui.dialogs.label_print_dialog.QMessageBox") as mock_box,
        ):
            dlg._print_labels()
            PrintWorker.instance().job_result.emit("job_label_1", True, "")
            mock_box.information.assert_called_once()
        dlg.deleteLater()


class TestDocumentBrowserViewReprintTiming:
    def test_no_success_before_job_completes(self, qapp, sale):
        view = DocumentBrowserView()
        view.current_doc = {"type": "sale", "id": sale.id, "document_number": sale.document_number}
        with (
            patch.object(PrintWorker, "add_job", return_value="job_doc_1"),
            patch("cbpos.ui.views.document_view.QMessageBox") as mock_box,
        ):
            view.reprint_document()
            mock_box.information.assert_not_called()
        view.deleteLater()

    def test_success_shown_once_job_completes(self, qapp, sale):
        view = DocumentBrowserView()
        view.current_doc = {"type": "sale", "id": sale.id, "document_number": sale.document_number}
        with (
            patch.object(PrintWorker, "add_job", return_value="job_doc_1"),
            patch("cbpos.ui.views.document_view.QMessageBox") as mock_box,
        ):
            view.reprint_document()
            PrintWorker.instance().job_result.emit("job_doc_1", True, "")
            mock_box.information.assert_called_once()
        view.deleteLater()


class TestHistoryViewReprintTiming:
    def test_no_success_before_job_completes(self, qapp, sale):
        view = HistoryView()
        view.current_sale = sale
        with (
            patch.object(PrintWorker, "add_job", return_value="job_hist_1"),
            patch("cbpos.ui.views.history_view.QMessageBox") as mock_box,
        ):
            view.reprint_receipt()
            mock_box.information.assert_not_called()
        view.deleteLater()

    def test_success_shown_once_job_completes(self, qapp, sale):
        view = HistoryView()
        view.current_sale = sale
        with (
            patch.object(PrintWorker, "add_job", return_value="job_hist_1"),
            patch("cbpos.ui.views.history_view.QMessageBox") as mock_box,
        ):
            view.reprint_receipt()
            PrintWorker.instance().job_result.emit("job_hist_1", True, "")
            mock_box.information.assert_called_once()
        view.deleteLater()

    def test_history_view_doc_selection_change_during_flight(self, qapp, sale):
        view = HistoryView()
        view.current_sale = sale
        other_sale = MagicMock(id=999, document_number="REC-OTHER")
        with (
            patch.object(PrintWorker, "add_job", return_value="job_hist_2"),
            patch("cbpos.ui.views.history_view.QMessageBox") as mock_box,
        ):
            view.reprint_receipt()
            view.current_sale = other_sale
            PrintWorker.instance().job_result.emit("job_hist_2", True, "")
            mock_box.information.assert_called_once()
            args, _ = mock_box.information.call_args
            assert sale.document_number in args[2]
        view.deleteLater()

    def test_history_view_reprint_none_reenables_button(self, qapp, sale):
        view = HistoryView()
        view.current_sale = sale
        with patch("cbpos.core.services.printer_service.PrinterService.print_receipt", return_value=None):
            view.reprint_receipt()
            assert view.reprint_btn.isEnabled() is True
        view.deleteLater()
