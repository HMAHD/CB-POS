"""Tests for atomic deletion of autosave on sale completion (Phase 10B.1 / #932)."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.models import (
    Product,
    Role,
    User,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.transaction_service import TransactionService


@pytest.fixture
def logged_in_cashier(db_session):
    """Create and log in a cashier user."""
    role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
    if not role:
        role = Role(name=ADMIN_ROLE_NAME)
        db_session.add(role)
        db_session.commit()

    user = db_session.query(User).filter_by(username="cashier_sale_test").first()
    if not user:
        user = User(username="cashier_sale_test", pin_hash="hash", role_id=role.id, is_active=True)
        db_session.add(user)
        db_session.commit()

    AuthService._current_user = user
    from cbpos.core.constants.features import Features
    from cbpos.core.services.feature_flags import FeatureFlags

    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, True, acting_user_id=user.id)
    yield user
    AuthService._current_user = None


@pytest.fixture
def sale_product(db_session):
    """Create a sample product with available stock."""
    prod = db_session.query(Product).filter_by(barcode="SALE-AUTO-01").first()
    if not prod:
        prod = Product(
            name_en="Sale Autosave Item",
            barcode="SALE-AUTO-01",
            price=Decimal("150.00"),
            cost=Decimal("90.00"),
            stock_qty=Decimal("100.000"),
            is_active=True,
        )
        db_session.add(prod)
        db_session.commit()
    return prod


@pytest.mark.domain
def test_issue_932_sale_completion_atomically_deletes_autosave(db_session, logged_in_cashier, sale_product):
    """Sale completion in process_sale atomically deletes the terminal's autosave record."""
    terminal_id = "TERM-SALE-01"
    ConfigService.set("terminal_id", terminal_id)

    cart = CartService()
    cart.add_item(sale_product, Decimal("2.000"))
    snap = CartAutosaveService.snapshot_cart(cart)
    CartAutosaveService.save(snap, terminal_id, 1)

    assert CartAutosaveService.has_autosave(terminal_id) is True

    payments = [{"method": "Cash", "amount": Decimal("300.00")}]
    sale = TransactionService.process_sale(cart, payments, customer_id=None)

    assert sale is not None
    # Autosave must be deleted atomically in the sale transaction
    assert CartAutosaveService.has_autosave(terminal_id) is False


@pytest.mark.domain
def test_issue_932_sale_failure_rollback_preserves_autosave(db_session, logged_in_cashier, sale_product):
    """If sale execution fails and rolls back, the autosave record is preserved."""
    terminal_id = "TERM-SALE-02"
    ConfigService.set("terminal_id", terminal_id)

    cart = CartService()
    cart.add_item(sale_product, Decimal("2.000"))
    snap = CartAutosaveService.snapshot_cart(cart)
    CartAutosaveService.save(snap, terminal_id, 1)

    assert CartAutosaveService.has_autosave(terminal_id) is True

    payments = [{"method": "Cash", "amount": Decimal("300.00")}]

    # Inject failure into _write_sale_lines to trigger rollback
    with patch.object(TransactionService, "_write_sale_lines", side_effect=RuntimeError("Simulated failure")):
        with pytest.raises(RuntimeError, match="Simulated failure"):
            TransactionService.process_sale(cart, payments, customer_id=None)

    # Autosave must still exist because transaction rolled back!
    assert CartAutosaveService.has_autosave(terminal_id) is True
