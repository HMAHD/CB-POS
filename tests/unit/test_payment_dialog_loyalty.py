"""Unit tests for loyalty points redemption in PaymentDialog."""

from decimal import Decimal

import pytest

from cbpos.core.models import Customer, PaymentMethod
from cbpos.core.services.config_service import ConfigService
from cbpos.ui.dialogs.payment_dialog import PaymentDialog


@pytest.fixture
def cash_method(db_session):
    cash = db_session.query(PaymentMethod).filter_by(name="Cash").first()
    if cash is None:
        cash = PaymentMethod(name="Cash", is_cash=True, is_active=True, shortcut="F12")
        db_session.add(cash)
        db_session.commit()
    return cash


@pytest.fixture
def customer_with_points(db_session):
    c = Customer(name="Loyal VIP", phone="0779998888", loyalty_points=350)
    db_session.add(c)
    db_session.commit()
    return c


class TestPaymentDialogLoyalty:
    """Test offscreen PyQt PaymentDialog loyalty display, redemption, and cancellation."""

    def test_loyalty_panel_hidden_when_disabled(self, qapp, cash_method, customer_with_points):
        ConfigService.set("enable_loyalty", False)
        dlg = PaymentDialog(Decimal("1000.00"), customer=customer_with_points)
        dlg.show()
        try:
            assert hasattr(dlg, "loyalty_frame")
            assert dlg.loyalty_frame.isHidden()
        finally:
            dlg.deleteLater()

    def test_loyalty_panel_visible_when_enabled(self, qapp, cash_method, customer_with_points):
        ConfigService.set("enable_loyalty", True)
        ConfigService.set("loyalty_point_value", "1.00")
        dlg = PaymentDialog(Decimal("1000.00"), customer=customer_with_points)
        dlg.show()
        try:
            assert hasattr(dlg, "loyalty_frame")
            assert not dlg.loyalty_frame.isHidden()
            assert "Loyal VIP" in dlg.lbl_loyalty_info.text()
            assert "350" in dlg.lbl_loyalty_info.text()
            assert not dlg.btn_redeem.isHidden()
            assert dlg.btn_cancel_redeem.isHidden()
        finally:
            dlg.deleteLater()

    def test_apply_redemption_updates_remaining_balance(self, qapp, cash_method, customer_with_points):
        ConfigService.set("enable_loyalty", True)
        ConfigService.set("loyalty_point_value", "1.00")
        ConfigService.set("loyalty_minimum_redeem", 50)

        dlg = PaymentDialog(Decimal("1000.00"), customer=customer_with_points)
        dlg.show()
        try:
            assert dlg.get_remaining_amount() == Decimal("1000.00")
            assert dlg.loyalty_points_redeemed == 0

            # Redeem 200 points = Rs. 200 discount
            dlg.apply_loyalty_redemption(200)

            assert dlg.loyalty_points_redeemed == 200
            assert dlg.get_remaining_amount() == Decimal("800.00")
            assert not dlg.lbl_redeemed.isHidden()
            assert "200" in dlg.lbl_redeemed.text()
            assert not dlg.btn_cancel_redeem.isHidden()
            assert dlg.btn_redeem.isHidden()

            # Add payment for remaining 800 covers bill
            dlg.select_method(dlg.payment_methods[0], dlg._method_buttons[0][0])
            dlg.txt_amount.setText("800.00")
            dlg.add_payment()

            assert dlg.get_remaining_amount() == Decimal("0.00")
            assert dlg.btn_finish.isEnabled()
        finally:
            dlg.deleteLater()

    def test_cancel_redemption_restores_balance(self, qapp, cash_method, customer_with_points):
        ConfigService.set("enable_loyalty", True)
        ConfigService.set("loyalty_point_value", "1.00")
        ConfigService.set("loyalty_minimum_redeem", 50)

        dlg = PaymentDialog(Decimal("1000.00"), customer=customer_with_points)
        dlg.show()
        try:
            dlg.apply_loyalty_redemption(200)
            assert dlg.get_remaining_amount() == Decimal("800.00")

            dlg.cancel_loyalty_redemption()
            assert dlg.loyalty_points_redeemed == 0
            assert dlg.get_remaining_amount() == Decimal("1000.00")
            assert dlg.lbl_redeemed.isHidden()
            assert dlg.btn_cancel_redeem.isHidden()
            assert not dlg.btn_redeem.isHidden()
        finally:
            dlg.deleteLater()
