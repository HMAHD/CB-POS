"""Domain tests for Issue #804: Recalled held bills lose line discounts, price overrides, notes, and bill discount."""

from decimal import Decimal

import pytest

from cbpos.core.database import Database
from cbpos.core.models import Product, SuspendedTransaction, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.suspended_transaction_service import RecallResult, SuspendedTransactionService

pytestmark = pytest.mark.domain


@pytest.fixture
def test_user(db_session):
    from cbpos.core.models import Role

    role = Role(name="HoldTestRole")
    db_session.add(role)
    db_session.flush()
    user = User(username="hold_cashier", pin_hash="hash", role_id=role.id)
    db_session.add(user)
    db_session.flush()
    return user


def test_issue_804_round_trip_keeps_discount_override_notes_cart_discount(db_session, test_user):
    """Held bill v2 format preserves line discounts, price overrides, notes, and cart discount."""
    p1 = Product(name_en="Item 1", barcode="HOLD01", price=Decimal("100.00"), stock_qty=Decimal("10"), is_active=True)
    p2 = Product(name_en="Item 2", barcode="HOLD02", price=Decimal("500.00"), stock_qty=Decimal("10"), is_active=True)
    db_session.add_all([p1, p2])
    db_session.commit()

    cart = CartService()
    cart.add_item(p1, qty=Decimal("2.0"))
    cart.apply_line_discount(0, "PERCENTAGE", Decimal("10.00"))
    cart.set_line_note(0, "Gift wrap please")

    cart.add_item(p2, qty=Decimal("1.0"))
    cart.override_price(1, Decimal("350.00"), user=test_user)

    cart.apply_cart_discount("FIXED", Decimal("30.00"))

    orig_totals = cart.get_totals()

    held_id = SuspendedTransactionService.hold_bill(cart, note="Table 5")
    assert held_id is not None

    recalled_cart = CartService()
    result = SuspendedTransactionService.recall_bill(held_id, recalled_cart)

    assert isinstance(result, RecallResult)
    assert result.ok is True
    assert len(recalled_cart.items) == 2

    # Check line 0
    item0 = recalled_cart.items[0]
    assert item0["product"].id == p1.id
    assert item0["qty"] == Decimal("2.0")
    assert item0["discount_type"] == "PERCENTAGE"
    assert item0["discount_value"] == Decimal("10.00")
    assert item0.get("note") == "Gift wrap please"

    # Check line 1 (override)
    item1 = recalled_cart.items[1]
    assert item1["product"].id == p2.id
    assert item1["qty"] == Decimal("1.0")
    assert item1["unit_price"] == Decimal("350.00")
    assert item1["is_manual_price"] is True
    assert item1.get("override_approved_by") == test_user.id

    # Check cart discount
    assert recalled_cart.cart_discount_type == "FIXED"
    assert recalled_cart.cart_discount_value == Decimal("30.00")

    # Final totals match
    recalled_totals = recalled_cart.get_totals()
    assert recalled_totals["final_total"] == orig_totals["final_total"]


def test_issue_804_price_changed_since_hold_keeps_held_price_with_notice(db_session):
    """When product price changed after hold, recall keeps held unit price and returns notice."""
    p = Product(name_en="Milk", barcode="HOLD_MILK", price=Decimal("200.00"), stock_qty=Decimal("10"), is_active=True)
    db_session.add(p)
    db_session.commit()

    cart = CartService()
    cart.add_item(p, qty=Decimal("1.0"))
    held_id = SuspendedTransactionService.hold_bill(cart)
    assert held_id is not None

    # Change product price in DB to 250.00
    with Database().get_session() as session:
        prod = session.get(Product, p.id)
        prod.price = Decimal("250.00")
        session.commit()

    recalled_cart = CartService()
    result = SuspendedTransactionService.recall_bill(held_id, recalled_cart)

    assert result.ok is True
    assert len(recalled_cart.items) == 1
    # Held price was kept
    assert recalled_cart.items[0]["unit_price"] == Decimal("200.00")
    # Notice was recorded
    assert len(result.notices) == 1
    assert "Milk" in result.notices[0]


def test_issue_804_legacy_rows_still_recall(db_session):
    """Legacy v1 held bills (plain list of dicts) still recall correctly."""
    import json

    p = Product(name_en="Bread", barcode="HOLD_BREAD", price=Decimal("150.00"), stock_qty=Decimal("10"), is_active=True)
    db_session.add(p)
    db_session.commit()

    with Database().get_session() as session:
        legacy_data = json.dumps([{"barcode": "HOLD_BREAD", "qty": "2.0"}])
        st = SuspendedTransaction(data=legacy_data, note="Legacy")
        session.add(st)
        session.commit()
        st_id = st.id

    recalled_cart = CartService()
    result = SuspendedTransactionService.recall_bill(st_id, recalled_cart)

    assert result.ok is True
    assert len(recalled_cart.items) == 1
    assert recalled_cart.items[0]["product"].id == p.id
    assert recalled_cart.items[0]["qty"] == Decimal("2.0")
    assert recalled_cart.items[0]["unit_price"] == Decimal("150.00")
