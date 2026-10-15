"""
#482: Roadmap 10.4 lists "Save as PDF: Digital copy" as a receipt option,
but receipt_options_dialog.py only had print/email/skip. InvoiceService
already generates a professional A4 PDF for any Sale (used for B2B tax
invoices via PrinterService) -- reuses it here behind a file-save dialog.
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
    permission = Permission(code=f"pdf_test_{suffix}")
    role = Role(name=f"PdfTestRole_{suffix}", permissions=[permission])
    user = User(username=f"pdf_test_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(name_en=f"PdfProduct_{_counter}", price=100.0, stock_qty=10.0, barcode=f"PDFB{_counter:04d}")
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def sale(db_session, test_user, test_product):
    global _counter
    _counter += 1
    sale = Sale(
        document_number=f"REC-PDF-{_counter}",
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


class TestSaveAsPdf:
    def test_button_exists(self, dialog):
        assert dialog.btn_save_pdf is not None

    def test_cancelling_the_file_dialog_does_not_generate_anything(self, dialog):
        with (
            patch("cbpos.ui.dialogs.receipt_options_dialog.QFileDialog.getSaveFileName", return_value=("", "")),
            patch("cbpos.ui.dialogs.receipt_options_dialog.InvoiceService") as mock_invoice_service,
        ):
            dialog.save_as_pdf()

        mock_invoice_service.generate_pdf.assert_not_called()

    def test_chosen_path_generates_the_pdf_for_the_real_sale(self, dialog, sale, tmp_path):
        target = str(tmp_path / "receipt.pdf")
        with (
            patch(
                "cbpos.ui.dialogs.receipt_options_dialog.QFileDialog.getSaveFileName",
                return_value=(target, "PDF Files (*.pdf)"),
            ),
            patch("cbpos.ui.dialogs.receipt_options_dialog.InvoiceService") as mock_invoice_service,
            patch("cbpos.ui.dialogs.receipt_options_dialog.QMessageBox.information") as mock_info,
        ):
            dialog.save_as_pdf()

        mock_invoice_service.generate_pdf.assert_called_once_with(sale, target)
        mock_info.assert_called_once()

    def test_generation_failure_shows_a_warning_not_a_crash(self, dialog, tmp_path):
        target = str(tmp_path / "receipt.pdf")
        with (
            patch(
                "cbpos.ui.dialogs.receipt_options_dialog.QFileDialog.getSaveFileName",
                return_value=(target, "PDF Files (*.pdf)"),
            ),
            patch(
                "cbpos.ui.dialogs.receipt_options_dialog.InvoiceService.generate_pdf",
                side_effect=RuntimeError("disk full"),
            ),
            patch("cbpos.ui.dialogs.receipt_options_dialog.QMessageBox.warning") as mock_warning,
        ):
            dialog.save_as_pdf()

        mock_warning.assert_called_once()

    def test_real_invoice_is_written_for_the_sale(self, dialog, tmp_path):
        """#740: the real generator used to raise AttributeError, so Save PDF only ever warned."""
        target = tmp_path / "receipt.pdf"
        with (
            patch(
                "cbpos.ui.dialogs.receipt_options_dialog.QFileDialog.getSaveFileName",
                return_value=(str(target), "PDF Files (*.pdf)"),
            ),
            patch("cbpos.ui.dialogs.receipt_options_dialog.QMessageBox.information") as mock_info,
            patch("cbpos.ui.dialogs.receipt_options_dialog.QMessageBox.warning") as mock_warning,
        ):
            dialog.save_as_pdf()

        mock_warning.assert_not_called()
        mock_info.assert_called_once()
        assert target.read_bytes().startswith(b"%PDF-")
