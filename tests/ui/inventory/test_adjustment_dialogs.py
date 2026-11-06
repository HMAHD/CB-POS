from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QLabel

from cbpos.core.models import Customer
from cbpos.ui.dialogs.adjust_balance_dialog import AdjustBalanceDialog
from cbpos.ui.dialogs.adjust_points_dialog import AdjustPointsDialog

pytestmark = pytest.mark.usefixtures("qapp")


def test_adjust_balance_dialog_modes(db_session):
    cust = Customer(
        name="Test Adjust Cust",
        current_debt=Decimal("2500.00"),
        credit_limit=Decimal("10000.00"),
    )
    db_session.add(cust)
    db_session.flush()

    dlg = AdjustBalanceDialog(cust)
    try:
        # Mode: Add to Debt (+500 on 2500 -> 3000)
        dlg.set_mode("add")
        dlg.amount_spin.setValue(500)
        assert dlg.calculate_new_balance() == Decimal("3000.00")
        assert dlg.calculate_delta() == Decimal("500.00")

        # Mode: Reduce Debt (-500 on 2500 -> 2000)
        dlg.set_mode("reduce")
        assert dlg.calculate_new_balance() == Decimal("2000.00")
        assert dlg.calculate_delta() == Decimal("-500.00")

        # Mode: Set Exact Debt (set 1000 on 2500 -> 1000)
        dlg.set_mode("set")
        dlg.amount_spin.setValue(1000)
        assert dlg.calculate_new_balance() == Decimal("1000.00")
        assert dlg.calculate_delta() == Decimal("-1500.00")
    finally:
        dlg.deleteLater()


def test_adjust_balance_dialog_requires_reason(db_session):
    cust = Customer(
        name="Test Reason Cust",
        current_debt=Decimal("2500.00"),
        credit_limit=Decimal("10000.00"),
    )
    db_session.add(cust)
    db_session.flush()

    dlg = AdjustBalanceDialog(cust)
    try:
        dlg.amount_spin.setValue(500)
        dlg.reason_edit.setText("")
        assert not dlg.validate()
        dlg.reason_edit.setText("Opening Balance Correction")
        assert dlg.validate()
    finally:
        dlg.deleteLater()


def test_adjust_points_dialog_modes(db_session):
    cust = Customer(
        name="Test Points Cust",
        loyalty_points=150,
    )
    db_session.add(cust)
    db_session.flush()

    dlg = AdjustPointsDialog(cust)
    try:
        # Add points
        dlg.set_mode("add")
        dlg.points_spin.setValue(50)
        assert dlg.calculate_new_balance() == 200
        assert dlg.calculate_delta() == 50

        # Deduct points
        dlg.set_mode("deduct")
        assert dlg.calculate_new_balance() == 100
        assert dlg.calculate_delta() == -50

        # Set exact points
        dlg.set_mode("set")
        dlg.points_spin.setValue(300)
        assert dlg.calculate_new_balance() == 300
        assert dlg.calculate_delta() == 150
    finally:
        dlg.deleteLater()


def test_adjust_points_dialog_prevents_negative_points(db_session):
    cust = Customer(
        name="Test Neg Cust",
        loyalty_points=50,
    )
    db_session.add(cust)
    db_session.flush()

    dlg = AdjustPointsDialog(cust)
    try:
        dlg.set_mode("deduct")
        dlg.points_spin.setValue(100)  # 50 - 100 = -50
        assert not dlg.validate()
        dlg.points_spin.setValue(30)  # 50 - 30 = 20
        dlg.reason_edit.setText("Bonus Correction")
        assert dlg.validate()
    finally:
        dlg.deleteLater()


def test_issue_888_adjust_balance_dialog_negative_debt_store_credit(db_session):
    """AdjustBalanceDialog displays negative balance as store credit (#888)."""
    cust = Customer(
        name="Store Credit Customer",
        current_debt=Decimal("-1000.00"),
        credit_limit=Decimal("10000.00"),
    )
    db_session.add(cust)
    db_session.flush()

    dlg = AdjustBalanceDialog(cust)
    try:
        debt_label = dlg.findChild(QLabel, "AdjustCustDebt")
        assert debt_label is not None
        assert "Store credit" in debt_label.text()
        assert "1,000.00" in debt_label.text()

        # Preview of reducing debt further results in store credit preview
        dlg.set_mode("reduce")
        dlg.amount_spin.setValue(100)
        assert dlg.calculate_new_balance() == Decimal("-1100.00")
        assert "Store credit" in dlg.lbl_preview.text()
    finally:
        dlg.deleteLater()


def test_issue_794_dialog_calls_service_with_user(db_session, monkeypatch):
    """#794: StockAdjustmentDialog validates input, checks permission, and calls adjust_stock."""
    from unittest.mock import MagicMock

    from cbpos.core.models import Product, User
    from cbpos.ui.dialogs.stock_adjustment_dialog import StockAdjustmentDialog

    product = Product(
        barcode="BC_ADJ_794",
        name_en="Adjustable Item",
        price=Decimal("250.00"),
        stock_qty=Decimal("20"),
        is_weighted=False,
    )
    db_session.add(product)
    db_session.flush()

    mock_service = MagicMock()
    mock_user = User(id=42, username="manager_user")

    monkeypatch.setattr(
        "cbpos.ui.dialogs.stock_adjustment_dialog.check_permission_with_override",
        lambda perm, parent: mock_user,
    )

    dlg = StockAdjustmentDialog(product, inventory_service=mock_service)
    try:
        # Default mode is remove, qty 1
        assert dlg.radio_remove.isChecked()
        dlg.qty_spin.setValue(3)
        dlg.cmb_reason.setCurrentIndex(dlg.cmb_reason.findData("DAMAGED"))
        dlg.txt_note.setText("Dropped on floor")

        dlg.save_adjustment()

        mock_service.adjust_stock.assert_called_once_with(
            product_id=product.id,
            qty_change=Decimal("-3"),
            reason="DAMAGED",
            user_id=42,
            note="Dropped on floor",
        )
    finally:
        dlg.deleteLater()


def test_issue_794_inventory_view_adjust_stock_action(db_session, monkeypatch):
    """#794: InventoryView has adjust_btn and open_stock_adjustment opens StockAdjustmentDialog."""
    from cbpos.core.models import Product
    from cbpos.ui.dialogs.stock_adjustment_dialog import StockAdjustmentDialog
    from cbpos.ui.views.inventory_view import InventoryView

    product = Product(
        barcode="BC_VIEW_794",
        name_en="View Adjustable Item",
        price=Decimal("150.00"),
        stock_qty=Decimal("15"),
    )
    db_session.add(product)
    db_session.flush()

    view = InventoryView()
    try:
        assert hasattr(view, "adjust_btn")
        assert view.adjust_btn.text() != ""

        # Select the product row in view table
        row_to_select = 0
        for r, p in enumerate(view.model.products):
            if p.id == product.id:
                row_to_select = r
                break
        view.table.selectRow(row_to_select)

        opened = []
        monkeypatch.setattr(StockAdjustmentDialog, "exec", lambda self: opened.append(self) or 1)

        view.open_stock_adjustment()
        assert len(opened) == 1
        assert opened[0].product.id == product.id
    finally:
        view.deleteLater()
