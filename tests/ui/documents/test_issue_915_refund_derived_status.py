"""
UI tests for Issue #915:
Refunded sales show derived 'Refunded' or 'Part refunded' status pills and guard action buttons.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind
from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, SalePayment, User
from cbpos.core.services.refund_service import RefundLineRequest, RefundService
from cbpos.i18n import _t
from cbpos.ui.dialogs.sale_history_dialog import SaleHistoryDialog
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.history_view import HistoryView

_seq = 0


@pytest.fixture
def auth_user(db_session):
    global _seq
    _seq += 1
    role = Role(name=f"Role915_{_seq}")
    db_session.add(role)
    db_session.flush()

    for code in (Permissions.SALES_REFUND, Permissions.SALES_VOID):
        perm = db_session.query(Permission).filter_by(code=code).first()
        if not perm:
            perm = Permission(code=code, description=code)
            db_session.add(perm)
        role.permissions.append(perm)

    user = User(username=f"user915_{_seq}", pin_hash="hash", role=role)
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_data(db_session, auth_user):
    prod = Product(
        name_en="Soap",
        barcode=f"BAR-915-{_seq}",
        price=Decimal("100.00"),
        stock_qty=Decimal("100"),
    )
    db_session.add(prod)
    db_session.flush()

    # Sale 1: Completed, not refunded
    s1 = Sale(
        document_number=f"INV-915-1-{_seq}",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=auth_user.id,
    )
    db_session.add(s1)
    db_session.flush()
    item1 = SaleItem(
        sale_id=s1.id,
        product_id=prod.id,
        qty=Decimal("2"),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("200.00"),
        original_price=Decimal("100.00"),
    )
    pay1 = SalePayment(
        sale_id=s1.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("200.00")
    )
    db_session.add_all([item1, pay1])

    # Sale 2: Completed, partially refunded
    s2 = Sale(
        document_number=f"INV-915-2-{_seq}",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=auth_user.id,
    )
    db_session.add(s2)
    db_session.flush()
    item2 = SaleItem(
        sale_id=s2.id,
        product_id=prod.id,
        qty=Decimal("2"),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("200.00"),
        original_price=Decimal("100.00"),
    )
    pay2 = SalePayment(
        sale_id=s2.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("200.00")
    )
    db_session.add_all([item2, pay2])

    # Sale 3: Completed, fully refunded
    s3 = Sale(
        document_number=f"INV-915-3-{_seq}",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=auth_user.id,
    )
    db_session.add(s3)
    db_session.flush()
    item3 = SaleItem(
        sale_id=s3.id,
        product_id=prod.id,
        qty=Decimal("1"),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("100.00"),
        original_price=Decimal("100.00"),
    )
    pay3 = SalePayment(
        sale_id=s3.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("100.00")
    )
    db_session.add_all([item3, pay3])
    db_session.commit()

    # Process partial refund on s2 (1 item)
    RefundService.refund(
        s2.id,
        [RefundLineRequest(sale_item_id=item2.id, qty=Decimal("1"))],
        reason="Partial",
        user_id=auth_user.id,
    )

    # Process full refund on s3 (1 item)
    RefundService.refund(
        s3.id,
        [RefundLineRequest(sale_item_id=item3.id, qty=Decimal("1"))],
        reason="Full",
        user_id=auth_user.id,
    )

    return {"user": auth_user, "s1": s1, "s2": s2, "s3": s3}


@pytest.mark.usefixtures("qapp")
class TestIssue915RefundDerivedStatusUI:
    """UI test suite for derived refund status and button guards."""

    def test_sale_history_dialog_pills_and_button_guards(self, test_data):
        dialog = SaleHistoryDialog()
        dialog._sales = [test_data["s1"], test_data["s2"], test_data["s3"]]
        dialog._populate_sales_table()

        # Check table status cells (column 4)
        status_unrefunded = dialog.sales_table.item(0, 4).text()
        status_partial = dialog.sales_table.item(1, 4).text()
        status_full = dialog.sales_table.item(2, 4).text()

        assert status_unrefunded == _t("sale_history.status_completed")
        assert status_partial == _t("history.pill_part_refunded")
        assert status_full == _t("history.pill_refunded")

        # Select s1 (unrefunded): refund button enabled
        cell_s1 = dialog.sales_table.item(0, 0)
        dialog._on_sale_selected(cell_s1)
        assert dialog.btn_refund.isEnabled()
        assert dialog.btn_refund.toolTip() == ""
        assert dialog.lbl_info_status.text() == _t("sale_history.status_completed")

        # Select s2 (partially refunded): refund button still enabled
        cell_s2 = dialog.sales_table.item(1, 0)
        dialog._on_sale_selected(cell_s2)
        assert dialog.btn_refund.isEnabled()
        assert dialog.btn_refund.toolTip() == ""
        assert dialog.lbl_info_status.text() == _t("history.pill_part_refunded")

        # Select s3 (fully refunded): refund button disabled with tooltip
        cell_s3 = dialog.sales_table.item(2, 0)
        dialog._on_sale_selected(cell_s3)
        assert not dialog.btn_refund.isEnabled()
        assert dialog.btn_refund.toolTip() == _t("history.refund_disabled_full")
        assert dialog.lbl_info_status.text() == _t("history.pill_refunded")

        dialog.deleteLater()

    def test_history_view_pills_and_button_guards(self, test_data):
        view = HistoryView()
        sales = [test_data["s1"], test_data["s2"], test_data["s3"]]
        view.populate_table(sales)

        # Check status column in transaction table (column 5)
        assert view.transaction_table.item(0, 5).text() == "COMPLETED"
        assert view.transaction_table.item(1, 5).text() == _t("history.pill_part_refunded")
        assert view.transaction_table.item(2, 5).text() == _t("history.pill_refunded")

        # Simulate selection of s1: refund enabled
        view.current_sale = test_data["s1"]
        view.on_selection_changed()
        # Row selection event
        view.transaction_table.selectRow(0)
        assert view.refund_btn.isEnabled()

        # Row selection of s3 (fully refunded): refund disabled
        view.transaction_table.selectRow(2)
        assert not view.refund_btn.isEnabled()
        assert view.refund_btn.toolTip() == _t("history.refund_disabled_full")

        view.deleteLater()

    def test_document_browser_view_action_guards(self, test_data):
        view = DocumentBrowserView()

        # 1. Unrefunded sale: refund enabled, void enabled
        doc_s1 = {
            "id": test_data["s1"].id,
            "type": "sale",
            "document_number": test_data["s1"].document_number,
            "status": DocumentStatus.COMPLETED,
        }
        view.update_action_buttons(doc_s1)
        assert view.refund_btn.isEnabled()
        assert view.void_btn.isEnabled()

        # 2. Partially refunded sale: refund enabled, void disabled
        doc_s2 = {
            "id": test_data["s2"].id,
            "type": "sale",
            "document_number": test_data["s2"].document_number,
            "status": DocumentStatus.COMPLETED,
        }
        view.update_action_buttons(doc_s2)
        assert view.refund_btn.isEnabled()
        assert not view.void_btn.isEnabled()
        assert view.void_btn.toolTip() == _t("history.void_disabled_refunded")

        # 3. Fully refunded sale: refund disabled, void disabled
        doc_s3 = {
            "id": test_data["s3"].id,
            "type": "sale",
            "document_number": test_data["s3"].document_number,
            "status": DocumentStatus.COMPLETED,
        }
        view.update_action_buttons(doc_s3)
        assert not view.refund_btn.isEnabled()
        assert view.refund_btn.toolTip() == _t("history.refund_disabled_full")
        assert not view.void_btn.isEnabled()
        assert view.void_btn.toolTip() == _t("history.void_disabled_refunded")

        # 4. Refund document: refund disabled, void disabled
        doc_refund = {
            "id": 9999,
            "type": "sale",
            "document_number": "RET-001",
            "payment_method": "REFUND",
            "refund_of_sale_id": test_data["s3"].id,
            "status": DocumentStatus.COMPLETED,
        }
        view.update_action_buttons(doc_refund)
        assert not view.refund_btn.isEnabled()
        assert not view.void_btn.isEnabled()
        assert view.void_btn.toolTip() == _t("history.void_disabled_is_refund")

        view.deleteLater()
