"""Tests for Issue #889: Documents refund must use shared authorized RefundDialog flow."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QDialog

from cbpos.core.models import Product, Role, Sale, SaleItem, User
from cbpos.core.services.refund_service import RefundService
from cbpos.ui.dialogs.refund_dialog import RefundDialog
from cbpos.ui.views.document_view import DocumentBrowserView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def sale_fixture(db_session):
    role = Role(name="Role_889")
    user = User(username="user_889", pin_hash="hash", role=role, is_active=True)
    product = Product(name_en="Prod 889", barcode="P889", price=Decimal("100.00"), stock_qty=10)
    db_session.add_all([role, user, product])
    db_session.flush()

    sale = Sale(
        document_number="REC-889-1",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        user_id=user.id,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.flush()

    item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("100.00"),
        original_price=Decimal("100.00"),
        subtotal=Decimal("100.00"),
    )
    db_session.add(item)
    db_session.commit()
    return sale


def test_issue_889_documents_refund_opens_shared_refund_dialog_with_sale_preselected(sale_fixture, monkeypatch):
    """The Documents Refund button must open RefundDialog with the sale preselected."""
    view = DocumentBrowserView()
    view.current_doc = {
        "id": sale_fixture.id,
        "type": "sale",
        "document_number": sale_fixture.document_number,
    }

    dialog_opened = []

    def mock_refund_dialog(parent):
        dlg = MagicMock(spec=RefundDialog)
        dlg.exec.return_value = QDialog.DialogCode.Accepted
        dialog_opened.append(dlg)
        return dlg

    monkeypatch.setattr("cbpos.ui.dialogs.refund_dialog.RefundDialog", mock_refund_dialog)
    # Also patch QMessageBox.question in case old unpatched code tries to show the legacy confirm box
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.question", lambda *a, **k: None)
    monkeypatch.setattr(view, "load_documents", lambda: None)

    view.process_refund()

    assert len(dialog_opened) == 1
    dialog_opened[0].load_sale.assert_called_once()
    loaded_sale = dialog_opened[0].load_sale.call_args[0][0]
    assert loaded_sale.id == sale_fixture.id


def test_issue_889_cancelling_override_creates_no_refund(sale_fixture, monkeypatch):
    """When a user without sales.refund cancels the manager override, no refund is created."""
    dlg = RefundDialog()
    dlg.load_sale(sale_fixture)

    # Override handler returns None (user cancelled the prompt)
    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent: None,
    )

    dlg.process_refund()

    # Verify no refund was recorded
    assert RefundService.refund_state(sale_fixture.id) == "NONE"
