"""Tests for Issue #835: Manager override authentication does not switch the current user session."""

from decimal import Decimal

import pytest

from cbpos.core.models import AuditLog, Permission, Product, Role, Sale, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.transaction_service import TransactionService


@pytest.fixture
def auth_users(db_session):
    """Seed a cashier and a manager user."""
    perm_sale = Permission(code="sales.create")
    perm_void = Permission(code="sales.void")

    role_cashier = Role(name="Cashier_Role_835", permissions=[perm_sale])
    role_manager = Role(name="Manager_Role_835", permissions=[perm_sale, perm_void])

    cashier = User(
        username="cashier_835",
        pin_hash=AuthService.hash_pin("0000"),
        role=role_cashier,
        is_active=True,
    )
    manager = User(
        username="manager_835",
        pin_hash=AuthService.hash_pin("5678"),
        role=role_manager,
        is_active=True,
    )

    db_session.add_all([perm_sale, perm_void, role_cashier, role_manager, cashier, manager])
    db_session.commit()

    yield cashier, manager

    # Reset AuthService current user after test
    AuthService._current_user = None


@pytest.fixture
def test_product_835(db_session):
    """Product for sale transaction."""
    prod = Product(
        name_en="Test Product 835",
        price=Decimal("150.00"),
        stock_qty=Decimal("20.0"),
        barcode="BAR835",
    )
    db_session.add(prod)
    db_session.commit()
    return prod


def test_issue_835_override_does_not_change_current_user(db_session, auth_users):
    """Manager override authenticates manager PIN without switching the current user session."""
    cashier, manager = auth_users

    # 1. Log in as cashier
    logged_in = AuthService.login("0000")
    assert logged_in is not None
    assert logged_in.username == cashier.username
    assert AuthService.get_current_user().id == cashier.id

    # 2. Authenticate manager override with manager PIN
    override_user = AuthService.authenticate_pin("5678")
    assert override_user is not None
    assert override_user.username == manager.username
    assert override_user.id == manager.id

    # 3. Current user MUST still be cashier
    assert AuthService.get_current_user() is not None
    assert AuthService.get_current_user().id == cashier.id
    assert AuthService.get_current_user().username == cashier.username

    # 4. Check audit logs
    login_logs = db_session.query(AuditLog).filter(AuditLog.event_type == "LOGIN", AuditLog.user_id == manager.id).all()
    assert len(login_logs) == 0, "No LOGIN audit row should be written for manager override"

    override_logs = (
        db_session.query(AuditLog).filter(AuditLog.event_type == "OVERRIDE_AUTH", AuditLog.user_id == manager.id).all()
    )
    assert len(override_logs) == 1, "Exactly one OVERRIDE_AUTH audit row should be written"
    assert override_logs[0].action == "Manager Override Authenticated"
    assert override_logs[0].details == f"for {cashier.username}"


def test_issue_835_sale_after_override_is_cashier_sale(db_session, auth_users, test_product_835):
    """Sale processed after a manager override records the cashier's user_id on the sale."""
    cashier, _ = auth_users

    # Log in as cashier
    AuthService.login("0000")
    assert AuthService.get_current_user().id == cashier.id

    # Manager override occurs
    override_user = AuthService.authenticate_pin("5678")
    assert override_user is not None

    # Complete a sale
    cart_service = CartService()
    cart_service.add_item(test_product_835, qty=Decimal("1.0"))
    payments = [{"method": "CASH", "amount": Decimal("150.00")}]

    sale = TransactionService.process_sale(cart_service, payments)
    assert sale is not None
    assert sale.user_id == cashier.id

    # Verify persisted in database
    db_sale = db_session.query(Sale).filter(Sale.id == sale.id).first()
    assert db_sale is not None
    assert db_sale.user_id == cashier.id


def test_issue_835_profile_wrong_users_pin_does_not_switch_session(db_session, auth_users):
    """Checking own PIN with another user's PIN returns False and does not switch session."""
    cashier, _ = auth_users

    # Log in as cashier
    AuthService.login("0000")
    assert AuthService.get_current_user().id == cashier.id

    # Trying to verify current PIN using manager's PIN returns False
    result_manager_pin = AuthService.check_own_pin(cashier.id, "5678")
    assert result_manager_pin is False
    assert AuthService.get_current_user().id == cashier.id

    # Verifying with actual PIN returns True
    result_correct_pin = AuthService.check_own_pin(cashier.id, "0000")
    assert result_correct_pin is True
    assert AuthService.get_current_user().id == cashier.id
