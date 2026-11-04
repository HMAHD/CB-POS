"""
Tests for RefundDialog (UI master-detail and partial refund interactions) (#812).
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

from cbpos.core.models import Customer, Permission, Product, Role, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.refund_service import RefundService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.ui.dialogs.refund_dialog import RefundDialog, RefundTenderOverrideDialog

_uid_seq = 0


@pytest.fixture
def manager_user(db_session):
    global _uid_seq
    _uid_seq += 1
    perm_refund = db_session.query(Permission).filter_by(code="sales.refund").first()
    if not perm_refund:
        perm_refund = Permission(code="sales.refund", description="Refund")
        db_session.add(perm_refund)

    perm_override = db_session.query(Permission).filter_by(code="sales.refund_override_tender").first()
    if not perm_override:
        perm_override = Permission(code="sales.refund_override_tender", description="Override Tender")
        db_session.add(perm_override)

    role = Role(name=f"RefundManagerRole_{_uid_seq}", permissions=[perm_refund, perm_override])
    user = User(username=f"mgr_{_uid_seq}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def sample_sale(db_session, manager_user):
    p1 = Product(
        name_en="Anchor Milk 400g", barcode=f"BAR-M-{_uid_seq}", price=Decimal("100.00"), stock_qty=Decimal("50")
    )
    p2 = Product(
        name_en="Sugar kg",
        barcode=f"BAR-S-{_uid_seq}",
        price=Decimal("120.00"),
        stock_qty=Decimal("50"),
        is_weighted=True,
    )
    c = Customer(name="Perera", credit_limit=Decimal("5000.00"), current_debt=Decimal("0.00"))
    db_session.add_all([p1, p2, c])
    db_session.flush()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=manager_user):
        cart = CartService()
        cart.add_item(p1, qty=Decimal("2.000"))  # 200.00
        cart.add_item(p2, qty=Decimal("1.500"))  # 180.00
        sale = TransactionService.process_sale(
            cart,
            [
                {"method": "Cash", "amount": Decimal("200.00")},
                {"method": "Credit", "amount": Decimal("180.00")},
            ],
            customer_id=c.id,
        )
    return sale


@pytest.mark.usefixtures("qapp")
class TestRefundDialogUI:
    """UI test suite for RefundDialog."""

    def test_load_sale_populates_table_and_initial_state(self, sample_sale):
        dialog = RefundDialog()
        dialog.load_sale(sample_sale)

        assert dialog.found_sale.id == sample_sale.id
        assert dialog.items_table.rowCount() == 2
        assert dialog.btn_return_all.isEnabled()
        assert dialog.btn_change_tender.isEnabled()
        assert not dialog.btn_refund.isEnabled()  # 0 qty initially selected
        assert dialog.lbl_status_banner.isVisible() is False

        # First item: 2 sold, 0 refunded, spinbox max 2
        item_name = dialog.items_table.item(0, 0).text()
        assert "Anchor Milk" in item_name
        sb1 = dialog._spinboxes[0]
        assert sb1 is not None
        assert sb1.maximum() == 2
        assert sb1.value() == 0

        # Second item: weighed, 1.500 sold, spinbox max 1.500
        sb2 = dialog._spinboxes[1]
        assert sb2 is not None
        assert pytest.approx(sb2.maximum(), 0.001) == 1.500
        assert sb2.value() == 0.000

        dialog.deleteLater()

    def test_spinbox_value_change_updates_preview(self, sample_sale):
        dialog = RefundDialog()
        dialog.load_sale(sample_sale)

        sb1 = dialog._spinboxes[0]
        sb1.setValue(1)  # 1 Anchor Milk = 100.00

        assert dialog.btn_refund.isEnabled()
        assert "100.00" in dialog.lbl_refund_total.text()
        assert "Cash" in dialog.lbl_give_back.text()
        assert "Credit" in dialog.lbl_give_back.text()
        assert "100.00" in dialog.btn_refund.text()

        dialog.deleteLater()

    def test_return_all_button(self, sample_sale):
        dialog = RefundDialog()
        dialog.load_sale(sample_sale)

        dialog.btn_return_all.click()

        sb1 = dialog._spinboxes[0]
        sb2 = dialog._spinboxes[1]
        assert sb1.value() == 2
        assert pytest.approx(sb2.value(), 0.001) == 1.500
        assert dialog.btn_refund.isEnabled()
        assert "380.00" in dialog.lbl_refund_total.text()

        dialog.deleteLater()

    def test_tender_override_dialog_workflow(self, sample_sale, manager_user):
        override_dlg = RefundTenderOverrideDialog(has_customer=True)
        assert override_dlg.rb_credit.isEnabled()
        assert override_dlg.rb_cash.isChecked()

        # Without reason, apply fails
        with patch.object(QMessageBox, "warning") as mock_warn:
            override_dlg._on_apply()
            assert mock_warn.called

        # With reason, succeeds
        override_dlg.txt_reason.setText("Customer requested cash instead of store credit")
        override_dlg._on_apply()
        assert override_dlg.selected_tender == "CASH"
        assert override_dlg.override_reason == "Customer requested cash instead of store credit"
        override_dlg.deleteLater()

    def test_tender_override_integration_in_refund_dialog(self, sample_sale, manager_user):
        dialog = RefundDialog()
        dialog.load_sale(sample_sale)
        dialog._spinboxes[0].setValue(1)

        with (
            patch("cbpos.ui.dialogs.refund_dialog.check_permission_with_override", return_value=manager_user),
            patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted),
        ):
            # Simulate override applied
            dialog._tender_override = "CASH"
            dialog._override_reason = "Customer insisted on cash"
            dialog._recalculate()

            assert "Overridden: CASH" in dialog.lbl_give_back.text()

        dialog.deleteLater()

    def test_process_refund_executes_service_and_accepts(self, sample_sale, manager_user):
        dialog = RefundDialog()
        dialog.load_sale(sample_sale)
        dialog._spinboxes[0].setValue(1)  # 1 milk
        dialog.txt_reason.setText("Customer returned milk")

        with (
            patch("cbpos.ui.dialogs.refund_dialog.check_permission_with_override", return_value=manager_user),
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
            patch.object(QMessageBox, "information") as mock_info,
            patch.object(dialog, "accept") as mock_accept,
        ):
            dialog.process_refund()
            assert mock_info.called
            assert mock_accept.called

        # Verify sale state is now PARTIAL
        assert RefundService.refund_state(sample_sale.id) == "PARTIAL"

        dialog.deleteLater()

    def test_fully_refunded_sale_shows_banner_and_disables_actions(self, db_session, sample_sale, manager_user):
        # Fully refund the sale first
        refundable = RefundService.refundable_lines(sample_sale.id)
        from cbpos.core.services.refund_service import RefundLineRequest

        RefundService.refund(
            sample_sale.id,
            [RefundLineRequest(sale_item_id=line.sale_item_id, qty=line.remaining_qty) for line in refundable],
            reason="Full return",
            user_id=manager_user.id,
        )

        dialog = RefundDialog()
        dialog.load_sale(sample_sale)

        assert not dialog.lbl_status_banner.isHidden()
        assert not dialog.btn_return_all.isEnabled()
        assert not dialog.btn_change_tender.isEnabled()
        assert not dialog.btn_refund.isEnabled()

        dialog.deleteLater()
