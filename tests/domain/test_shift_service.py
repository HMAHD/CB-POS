"""
Unit tests for ShiftService — shift lifecycle (start, get, close).
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.status import ShiftStatus
from cbpos.core.models import Permission, Role, Shift, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.shift_service import ShiftService
from cbpos.core.services.transaction_service import TransactionService

# ── Shared Fixtures ──────────────────────────────────────────────────────

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_user(db_session):
    """Create a test user for shift tests."""
    suffix = _next_suffix()
    permission = Permission(code=f"shift_test_{suffix}")
    role = Role(name=f"ShiftRole_{suffix}", permissions=[permission])
    user = User(username=f"shift_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def shift_service():
    """Create a ShiftService instance."""
    return ShiftService()


# ── Test: start_shift ────────────────────────────────────────────────────


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_start_shift(mock_config, db_session, test_user, shift_service):
    """Starting a shift creates a new open shift with the float amount."""
    shift = shift_service.start_shift(test_user.id, Decimal("5000.00"))

    assert shift is not None
    assert shift.user_id == test_user.id
    assert shift.starting_cash == Decimal("5000.00")
    assert shift.status == ShiftStatus.OPEN
    assert shift.terminal_id == "TERM-01"


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_start_shift_duplicate(mock_config, db_session, test_user, shift_service):
    """Starting a shift when one is already open raises ValueError."""
    shift_service.start_shift(test_user.id, Decimal("5000.00"))

    with pytest.raises(ValueError, match="already has an open shift"):
        shift_service.start_shift(test_user.id, Decimal("3000.00"))


# ── Test: get_current_shift ──────────────────────────────────────────────


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_get_current_shift(mock_config, db_session, test_user, shift_service):
    """get_current_shift returns the open shift for the user."""
    shift_service.start_shift(test_user.id, Decimal("5000.00"))

    current = shift_service.get_current_shift(test_user.id)

    assert current is not None
    assert current.user_id == test_user.id
    assert current.status == ShiftStatus.OPEN


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_get_current_shift_none(mock_config, db_session, test_user, shift_service):
    """get_current_shift returns None when no shift is open."""
    current = shift_service.get_current_shift(test_user.id)
    assert current is None


# ── Test: close_shift ────────────────────────────────────────────────────


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_close_shift(mock_config, db_session, test_user, shift_service):
    """Closing a shift sets status to CLOSED and returns summary with variance."""
    shift = shift_service.start_shift(test_user.id, Decimal("5000.00"))

    summary = shift_service.close_shift(shift.id, counted_cash=Decimal("5200.00"), notes="All good")

    assert summary is not None
    assert summary["starting_cash"] == Decimal("5000.00")
    assert summary["actual_cash"] == Decimal("5200.00")
    assert summary["variance"] == Decimal("200.00")
    assert summary["notes"] == "All good"
    assert summary["end_time"] is not None

    # Verify shift is now closed in DB
    db_session.expire_all()
    closed_shift = db_session.get(Shift, shift.id)
    assert closed_shift.status == ShiftStatus.CLOSED
    assert closed_shift.notes == "All good"


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_close_shift_persists_reason_category(mock_config, db_session, test_user, shift_service):
    """Closing a shift with a variance persists both the reason category and notes to the DB.

    Regression test for #457: the dialog required a reason on variance, but
    close_shift() silently discarded it instead of writing it to the shift row.
    """
    shift = shift_service.start_shift(test_user.id, Decimal("5000.00"))

    shift_service.close_shift(
        shift.id,
        counted_cash=Decimal("4950.00"),
        notes="Miscounted the drawer at open",
        reason_category="MISCOUNTED",
    )

    db_session.expire_all()
    closed_shift = db_session.get(Shift, shift.id)
    assert closed_shift.reason_category == "MISCOUNTED"
    assert closed_shift.notes == "Miscounted the drawer at open"


# ── Issue #802 & #885 Regression Tests ───────────────────────────────────


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_issue_802_bank_transfer_counted_in_transfer_total(mock_config, db_session, test_user, shift_service):
    """Shift summary must count 'Bank Transfer' sales in transfer_sales using method_kind.

    Regression test for #802: shift summary looked up literal 'Transfer', missing
    'Bank Transfer' used in standard database setups.
    """
    from cbpos.core.constants.status import PaymentMethodKind
    from cbpos.core.models import PaymentMethod, Product
    from cbpos.core.services.cart_service import CartService
    from cbpos.core.services.transaction_service import TransactionService

    shift = shift_service.start_shift(test_user.id, Decimal("1000.00"))

    # Ensure "Bank Transfer" exists with kind TRANSFER
    bt = db_session.query(PaymentMethod).filter_by(name="Bank Transfer").first()
    if not bt:
        bt = PaymentMethod(name="Bank Transfer", kind=PaymentMethodKind.TRANSFER, is_active=True)
        db_session.add(bt)
    else:
        bt.kind = PaymentMethodKind.TRANSFER
    db_session.commit()

    suffix = _next_suffix()
    product = Product(
        name_en=f"Transfer Product {suffix}",
        barcode=f"TRF_{suffix}",
        price=Decimal("750.00"),
        stock_qty=Decimal("10.000"),
    )
    db_session.add(product)
    db_session.commit()

    cart = CartService()
    cart.add_item(product, qty=Decimal("1.000"))

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        sale = TransactionService.process_sale(
            cart,
            [{"method": "Bank Transfer", "amount": Decimal("750.00")}],
            customer_id=None,
        )

    assert sale is not None
    summary = shift_service.get_shift_summary(shift.id)
    assert summary["transfer_sales"] == Decimal("750.00")


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_issue_885_renamed_and_second_cash_methods_count(mock_config, db_session, test_user, shift_service):
    """Expected cash and cash_sales must count all methods with kind CASH, even if renamed or extra.

    Regression test for #885: shift summary only matched literal name 'Cash'.
    """
    from cbpos.core.constants.status import PaymentMethodKind
    from cbpos.core.models import PaymentMethod, Product
    from cbpos.core.services.cart_service import CartService
    from cbpos.core.services.transaction_service import TransactionService

    shift = shift_service.start_shift(test_user.id, Decimal("1000.00"))

    # Rename built-in "Cash" to "Salli" (kind CASH) and add "Cash USD" (kind CASH)
    cash_method = db_session.query(PaymentMethod).filter_by(name="Cash").first()
    if cash_method:
        cash_method.name = "Salli"
        cash_method.kind = PaymentMethodKind.CASH
    else:
        cash_method = PaymentMethod(name="Salli", kind=PaymentMethodKind.CASH, is_cash=True, is_active=True)
        db_session.add(cash_method)

    usd_cash = db_session.query(PaymentMethod).filter_by(name="Cash USD").first()
    if not usd_cash:
        usd_cash = PaymentMethod(name="Cash USD", kind=PaymentMethodKind.CASH, is_cash=True, is_active=True)
        db_session.add(usd_cash)
    db_session.commit()

    suffix = _next_suffix()
    product = Product(
        name_en=f"Cash Product {suffix}",
        barcode=f"CSH_{suffix}",
        price=Decimal("200.00"),
        stock_qty=Decimal("10.000"),
    )
    db_session.add(product)
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart1 = CartService()
        cart1.add_item(product, qty=Decimal("1.000"))
        TransactionService.process_sale(cart1, [{"method": "Salli", "amount": Decimal("200.00")}])

        cart2 = CartService()
        cart2.add_item(product, qty=Decimal("1.000"))
        TransactionService.process_sale(cart2, [{"method": "Cash USD", "amount": Decimal("200.00")}])

    summary = shift_service.get_shift_summary(shift.id)
    assert summary["cash_sales"] == Decimal("400.00")
    assert summary["expected_cash"] == Decimal("1000.00") + Decimal("400.00")


@pytest.mark.xfail(reason="fixed by 3A.3 refund engine (#812)", strict=True)
def test_issue_850_cash_refund_reduces_expected_cash(db_session, test_user, test_product):
    """Refunding a cash sale in the same shift reduces expected cash back to the starting float."""
    shift_service = ShiftService()
    shift = shift_service.start_shift(test_user.id, Decimal("0.00"))

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(test_product, qty=Decimal("20.000"))  # 20 * 100 = 2000.00
        sale = TransactionService.process_sale(cart, [{"method": "Cash", "amount": Decimal("2000.00")}])
        assert sale is not None

        summary_before = shift_service.get_shift_summary(shift.id)
        assert summary_before["expected_cash"] == Decimal("2000.00")

        refund_success = TransactionService.process_refund(sale.id, "Customer return", test_user.id)
        assert refund_success is True

    summary_after = shift_service.get_shift_summary(shift.id)
    assert summary_after["cash_sales"] == Decimal("0.00")
    assert summary_after["expected_cash"] == Decimal("0.00")
