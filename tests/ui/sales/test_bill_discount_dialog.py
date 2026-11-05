from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QDialog

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.bill_discount_dialog import BillDiscountDialog
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


def _make_mock_product(pid=1, price="500.00"):
    p = MagicMock()
    p.id = pid
    p.name_en = f"Product {pid}"
    p.barcode = f"BAR{pid:03d}"
    p.price = Decimal(price)
    p.stock_qty = Decimal("10")
    p.unit = None
    return p


@pytest.mark.ui
def test_issue_813_bill_discount_dialog_preview_and_toggle(qapp):
    """BillDiscountDialog calculates live preview and toggles between % and Amount."""
    dlg = BillDiscountDialog(
        current_subtotal=Decimal("2000.00"),
        current_type="NONE",
        current_value=Decimal("0.00"),
        max_discount_pct=Decimal("15.0"),
    )
    assert dlg.objectName() == "BillDiscountDialog"
    assert not dlg.spin_value.isHidden()

    # Enter 10%
    dlg.spin_value.setValue(10.0)
    disc_type, disc_val = dlg.get_data()
    assert disc_type == "PERCENTAGE"
    assert disc_val == Decimal("10.00")
    assert "2,000.00" in dlg.lbl_preview.text()
    assert "1,800.00" in dlg.lbl_preview.text()
    assert dlg.lbl_cap_warning.isHidden()

    # Enter 20% (over 15% cap)
    dlg.spin_value.setValue(20.0)
    assert not dlg.lbl_cap_warning.isHidden()

    # Switch to fixed amount
    dlg.rb_fixed.click()
    disc_type, disc_val = dlg.get_data()
    assert disc_type == "FIXED"
    dlg.spin_value.setValue(500.0)
    assert "1,500.00" in dlg.lbl_preview.text()

    dlg.close()


@pytest.mark.ui
def test_issue_813_bill_discount_dialog_remove(qapp):
    """When a discount exists, 'Remove discount' button removes it."""
    dlg = BillDiscountDialog(
        current_subtotal=Decimal("2000.00"),
        current_type="PERCENTAGE",
        current_value=Decimal("10.00"),
        max_discount_pct=Decimal("15.0"),
    )
    assert dlg.btn_remove is not None
    assert not dlg.btn_remove.isHidden()

    dlg.btn_remove.click()
    assert dlg.result() == QDialog.DialogCode.Accepted
    disc_type, disc_val = dlg.get_data()
    assert disc_type == "NONE"
    assert disc_val == Decimal("0.00")


@pytest.mark.ui
def test_issue_813_dialog_keyboard_flow(qapp, db_session):
    """SalesView: Ctrl+B shortcut triggers bill discount and updates cart display."""
    user = MagicMock(id=1, username="cashier")
    with (
        patch("cbpos.core.utils.permission_helper.check_permission_with_override", return_value=user),
        patch("cbpos.core.services.logging_service.LoggingService.log_action"),
        patch(
            "cbpos.ui.dialogs.bill_discount_dialog.BillDiscountDialog.exec", return_value=QDialog.DialogCode.Accepted
        ),
        patch(
            "cbpos.ui.dialogs.bill_discount_dialog.BillDiscountDialog.get_data",
            return_value=("PERCENTAGE", Decimal("10.00")),
        ),
    ):
        view = SalesView()
        product = _make_mock_product(1, "1000.00")
        view.cart_service.add_item(product, Decimal("2"))  # 2000.00
        view.update_cart_display()

        # Trigger bill discount
        view.shortcut_ctrl_b.activated.emit()

        totals = view.cart_service.get_totals()
        assert totals["cart_discount"] == Decimal("200.00")
        assert totals["final_total"] == Decimal("1800.00")
        assert not view.lbl_discount.isHidden()
        assert "200.00" in view.lbl_discount.text()

        view.deleteLater()
