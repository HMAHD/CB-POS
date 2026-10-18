from decimal import Decimal

import pytest

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
