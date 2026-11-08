"""UI regression tests for Issue #911 — Reprint authorisation and document truth."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, User
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.receipt_reprint_dialog import ReceiptReprintDialog
from cbpos.ui.dialogs.sale_history_dialog import SaleHistoryDialog
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.widgets.status_pill_delegate import STATUS_MEANING_ROLE


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def test_user(db_session):
    perm_reprint = db_session.query(Permission).filter_by(code=Permissions.SALES_REPRINT).first()
    if not perm_reprint:
        perm_reprint = Permission(code=Permissions.SALES_REPRINT)
        db_session.add(perm_reprint)
    role = Role(name="ReprintRole_911_UI", permissions=[perm_reprint])
    user = User(username="reprint_ui_user", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user):
        yield user


@pytest.fixture
def sample_sales(db_session, test_user):
    prod = Product(name_en="Item_911_UI", price=Decimal("100"), stock_qty=Decimal("10"), barcode="UI911")
    db_session.add(prod)
    db_session.flush()

    sale_ok = Sale(
        document_number="INV-2026-OK",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=test_user.id,
    )
    item_ok = SaleItem(
        product=prod,
        qty=Decimal("1.000"),
        unit_price=Decimal("100.00"),
        original_price=Decimal("100.00"),
        subtotal=Decimal("100.00"),
    )
    sale_ok.items = [item_ok]

    sale_void = Sale(
        document_number="INV-2026-VOID-UI",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        payment_method="CASH",
        status="VOID",
        user_id=test_user.id,
    )
    item_void = SaleItem(
        product=prod,
        qty=Decimal("1.000"),
        unit_price=Decimal("100.00"),
        original_price=Decimal("100.00"),
        subtotal=Decimal("100.00"),
    )
    sale_void.items = [item_void]

    db_session.add_all([sale_ok, item_ok, sale_void, item_void])
    db_session.commit()
    return sale_ok, sale_void


def test_issue_911_reprint_dialog_void_sale_greyed_out_and_button_disabled(qapp, sample_sales):
    """ReceiptReprintDialog shows VOID sale greyed out with VOID pill; button disabled with tooltip (#911)."""
    sale_ok, sale_void = sample_sales
    dlg = ReceiptReprintDialog()
    dlg.results = [sale_ok, sale_void]
    dlg._populate_table()

    # Table has 6 columns, with Status as column 5
    assert dlg.results_table.columnCount() == 6

    # Row 1 is VOID
    status_item = dlg.results_table.item(1, 5)
    assert status_item is not None
    assert status_item.data(STATUS_MEANING_ROLE) == "danger"
    assert status_item.text() == _t("sale_history.status_void")

    # Cells in row 1 are greyed out
    for col in range(5):
        cell = dlg.results_table.item(1, col)
        assert cell is not None
        assert cell.foreground().color() == Qt.GlobalColor.gray

    # Selecting row 1 (VOID) disables reprint button with tooltip
    dlg.results_table.setCurrentCell(1, 1)
    assert dlg.btn_reprint.isEnabled() is False
    assert dlg.btn_reprint.toolTip() == _t("reprint.void_blocked")

    # Selecting row 0 (COMPLETED) enables reprint button
    dlg.results_table.setCurrentCell(0, 1)
    assert dlg.btn_reprint.isEnabled() is True
    assert dlg.btn_reprint.toolTip() == ""
    dlg.deleteLater()


def test_issue_911_reprint_dialog_reprint_selected_blocks_void(qapp, sample_sales):
    """reprint_selected() warns and refuses when VOID sale is selected (#911)."""
    _, sale_void = sample_sales
    dlg = ReceiptReprintDialog()
    dlg.results = [sale_void]
    dlg._populate_table()
    dlg.results_table.setCurrentCell(0, 1)

    with (
        patch("cbpos.ui.dialogs.receipt_reprint_dialog.QMessageBox.warning") as mock_warn,
        patch.object(PrintWorker, "add_job") as mock_add_job,
    ):
        dlg.reprint_selected()
        mock_warn.assert_called_once()
        assert _t("reprint.void_blocked") in str(mock_warn.call_args)
        mock_add_job.assert_not_called()
    dlg.deleteLater()


def test_issue_911_reprint_dialog_permission_denied_cancels_reprint(qapp, sample_sales):
    """reprint_selected() aborts without printing when permission override is denied (#911)."""
    sale_ok, _ = sample_sales
    dlg = ReceiptReprintDialog()
    dlg.results = [sale_ok]
    dlg._populate_table()
    dlg.results_table.setCurrentCell(0, 1)

    with (
        patch("cbpos.core.utils.permission_helper.check_permission_with_override", return_value=None),
        patch("cbpos.core.services.receipt_reprint_service.ReceiptReprintService.reprint") as mock_reprint,
        patch.object(PrintWorker, "add_job") as mock_add_job,
    ):
        dlg.reprint_selected()
        mock_reprint.assert_not_called()
        mock_add_job.assert_not_called()
    dlg.deleteLater()


def test_issue_911_sale_history_void_disables_reprint_button(qapp, sample_sales):
    """SaleHistoryDialog disables Reprint button with tooltip when viewing a VOID sale (#911)."""
    sale_ok, sale_void = sample_sales
    with (
        patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]),
        patch("cbpos.ui.dialogs.sale_history_dialog.RefundService.refund_states", return_value={}),
    ):
        dlg = SaleHistoryDialog()

    dlg._sales = [sale_ok, sale_void]
    dlg._populate_sales_table()

    # Load VOID sale (row 1)
    dlg.sales_table.setCurrentCell(1, 0)
    assert dlg.btn_reprint.isEnabled() is False
    assert dlg.btn_reprint.toolTip() == _t("reprint.void_blocked")

    # Load COMPLETED sale (row 0)
    dlg.sales_table.setCurrentCell(0, 0)
    assert dlg.btn_reprint.isEnabled() is True
    assert dlg.btn_reprint.toolTip() == ""
    dlg.deleteLater()


def test_issue_911_document_browser_void_disables_reprint_button(qapp, sample_sales):
    """DocumentBrowserView disables reprint button with tooltip when document status is VOID (#911)."""
    _, sale_void = sample_sales
    view = DocumentBrowserView()

    doc_void = {
        "id": sale_void.id,
        "type": "sale",
        "document_number": sale_void.document_number,
        "status": DocumentStatus.VOID,
    }
    view.update_action_buttons(doc_void)
    assert view.reprint_btn.isEnabled() is False
    assert view.reprint_btn.toolTip() == _t("reprint.void_blocked")

    doc_ok = {
        "id": 1,
        "type": "sale",
        "document_number": "INV-2026-OK",
        "status": DocumentStatus.COMPLETED,
    }
    view.update_action_buttons(doc_ok)
    assert view.reprint_btn.isEnabled() is True
    assert view.reprint_btn.toolTip() == ""
    view.deleteLater()


def test_issue_911_document_browser_reprint_routes_to_service(qapp, sample_sales, test_user):
    """DocumentBrowserView.reprint_document() routes through ReceiptReprintService (#911)."""
    sale_ok, _ = sample_sales
    view = DocumentBrowserView()
    view.current_doc = {
        "id": sale_ok.id,
        "type": "sale",
        "document_number": sale_ok.document_number,
        "status": DocumentStatus.COMPLETED,
    }

    mock_job = MagicMock(commands=[{"type": "text", "val": "DUPLICATE"}])
    with (
        patch(
            "cbpos.core.services.receipt_reprint_service.ReceiptReprintService.reprint", return_value=mock_job
        ) as mock_svc,
        patch.object(PrintWorker, "add_job") as mock_add_job,
        patch("cbpos.ui.views.document_view.QMessageBox") as mock_box,
    ):
        view.reprint_document()
        mock_svc.assert_called_once_with(
            sale_ok.id,
            user_id=test_user.id,
            approver_id=None,
        )
        mock_add_job.assert_called_once_with("print_receipt", mock_job.commands)
        mock_box.critical.assert_not_called()
    view.deleteLater()
