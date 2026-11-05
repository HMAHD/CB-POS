"""
Unit tests for TransactionService — atomic commits, void, and refund workflows.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Customer, Permission, Product, Role, Sale, SaleItem, StockMovement, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.services.transaction_service import TransactionService

# ── Shared Fixtures ──────────────────────────────────────────────────────

_counter = 0


@pytest.fixture
def test_user(db_session):
    """Create a test user with a unique role and permission."""
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"txn_test_{suffix}")
    role = Role(name=f"TxnRole_{suffix}", permissions=[permission])
    user = User(username=f"txn_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    """Create a test product with stock."""
    global _counter
    _counter += 1
    product = Product(
        name_en=f"Product_{_counter}",
        price=100.0,
        stock_qty=10.0,
        barcode=f"TST{_counter:04d}",
    )
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def completed_sale(db_session, test_user, test_product):
    """Create a completed sale with one item (qty=2, price=100, total=200)."""
    sale = Sale(
        document_number=f"REC-FIX-{_counter}",
        date=datetime.now(),
        total_amount=200.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=200,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=test_product.id,
        qty=2.0,
        unit_price=100.0,
        original_price=100.0,
        subtotal=200.0,
    )
    db_session.add(sale_item)
    db_session.commit()
    return sale


# ── Test Case A: Atomic Commit (Sale + Stock) ───────────────────────────


def test_process_sale_atomic(db_session, test_user, test_product):
    """Sale processing is atomic: stock deducted, sale saved."""
    db_session.commit()

    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
    ):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        result = TransactionService.process_sale(cart_service, payments)

        assert result is not None

        db_session.refresh(test_product)
        assert test_product.stock_qty == 8.0

        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        assert sale is not None
        assert sale.total_amount == 200.0
        assert sale.items[0].qty == 2.0


def test_process_sale_persists_the_cart_line_note(db_session, test_user, test_product):
    """#481: the cart already captured a per-line note (add_line_note in
    sales_view.py) but SaleItem had no column for it -- the note was
    silently discarded the instant the sale completed."""
    db_session.commit()

    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
    ):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("1.0"))
        cart_service.items[0]["note"] = "Gift wrap please"
        payments = [{"method": "CASH", "amount": Decimal("100.0")}]

        TransactionService.process_sale(cart_service, payments)

        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        assert sale.items[0].notes == "Gift wrap please"


def test_process_sale_rollback_on_error(db_session, test_user, test_product):
    """Transaction rolls back on error — stock unchanged."""
    db_session.commit()

    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
    ):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        with patch(
            "cbpos.core.services.transaction_service.SaleItem",
            side_effect=RuntimeError("DB Error"),
        ):
            with pytest.raises(RuntimeError):
                TransactionService.process_sale(cart_service, payments)

            db_session.refresh(test_product)
            assert test_product.stock_qty == 10.0


# ── Test Case B: Backward Tax Verification ───────────────────────────────


def test_calculate_taxes():
    """TaxService backward calculation returns expected keys and types."""
    amount = Decimal("1000.00")
    taxes = TaxService.calculate_taxes(amount)

    assert "vat" in taxes
    assert "sscl" in taxes
    assert "net" in taxes
    assert isinstance(taxes["vat"], Decimal)


# ── Test Case C: Void Sale ───────────────────────────────────────────────


def test_void_sale(db_session, test_user, test_product, completed_sale):
    """Void sale sets status to VOID and restores stock."""
    result = TransactionService.void_sale(completed_sale.id, test_user.id, "Wrong Entry")

    assert result is True

    db_session.refresh(completed_sale)
    assert completed_sale.status == "VOID"

    db_session.refresh(test_product)
    assert test_product.stock_qty == 12.0  # 10 + 2 restored


# ── Test Case D: Double Void Prevention ──────────────────────────────────


def test_void_sale_already_voided(db_session, test_user, test_product):
    """Voiding an already-voided sale returns False."""
    sale = Sale(
        document_number=f"REC-VD-{_counter}",
        date=datetime.now(),
        total_amount=50.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=50,
        payment_method="CASH",
        status="VOID",
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=test_product.id,
        qty=1.0,
        unit_price=50.0,
        original_price=50.0,
        subtotal=50.0,
    )
    db_session.add(sale_item)
    db_session.commit()

    result = TransactionService.void_sale(sale.id, test_user.id, "Accidental double void")
    assert result is False

    db_session.refresh(test_product)
    assert test_product.stock_qty == 10.0


# ── Test Case E: Void Non-existent Sale ──────────────────────────────────


def test_void_nonexistent_sale(db_session):
    """Voiding a non-existent sale ID returns False."""
    result = TransactionService.void_sale(999999, 1, "Does not exist")
    assert result is False


# ── Test Case F: Void Stock Restoration Audit Trail ──────────────────────


def test_void_creates_stock_movements(db_session, test_user, test_product, completed_sale):
    """Voiding a sale creates VOID stock movements to restore inventory."""
    result = TransactionService.void_sale(completed_sale.id, test_user.id, "Customer changed mind")
    assert result is True

    void_movements = (
        db_session.query(StockMovement)
        .filter(StockMovement.product_id == test_product.id, StockMovement.type == "VOID")
        .all()
    )
    assert len(void_movements) >= 1
    last_void = void_movements[-1]
    assert last_void.qty_change == Decimal("2")

    db_session.refresh(test_product)
    assert test_product.stock_qty == 12.0  # 10 + 2


# ── Test Case G: Refund Full Workflow ────────────────────────────────────


def test_process_refund(db_session, test_user, test_product, completed_sale, peripherals):
    """Full refund creates a negative sale, restores stock, links to original, and reports it to the hardware."""
    with patch("cbpos.core.services.transaction_service.ConfigService.get_all", return_value={"language": "en"}):
        result = TransactionService.process_refund(completed_sale.id, "Defective item", test_user.id)

    assert result is True

    refund_sale = db_session.query(Sale).filter(Sale.refund_of_sale_id == completed_sale.id).first()
    (event,) = peripherals.events
    assert event.refund_sale.id == refund_sale.id
    assert event.voucher
    assert refund_sale is not None
    assert refund_sale.total_amount == Decimal("-200")
    assert refund_sale.payment_method == "REFUND"
    assert refund_sale.document_number.startswith("CN-")  # #637: sequential, was REF-<uuid>

    refund_items = db_session.query(SaleItem).filter(SaleItem.sale_id == refund_sale.id).all()
    assert len(refund_items) == 1
    assert refund_items[0].qty == Decimal("-2")

    db_session.refresh(test_product)
    assert test_product.stock_qty == 12.0  # 10 + 2


# ── Test Case H: Cannot Refund Voided Sale ───────────────────────────────


def test_refund_voided_sale_fails(db_session, test_user):
    """Cannot refund a sale that has been voided."""
    sale = Sale(
        document_number=f"REC-RV-{_counter}",
        date=datetime.now(),
        total_amount=100.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=100,
        payment_method="CASH",
        status="VOID",
    )
    db_session.add(sale)
    db_session.commit()

    with pytest.raises(ValueError, match="Cannot refund a voided sale"):
        TransactionService.process_refund(sale.id, "Should fail", test_user.id)


# ── Test Case I: Cannot Double-Refund ────────────────────────────────────


def test_double_refund_fails(db_session, test_user, test_product, completed_sale):
    """Cannot refund a sale that has already been refunded."""
    # Create existing refund
    existing_refund = Sale(
        document_number=f"REF-DR-{_counter}",
        date=datetime.now(),
        total_amount=-200.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=-200,
        payment_method="REFUND",
        refund_of_sale_id=completed_sale.id,
    )
    db_session.add(existing_refund)
    db_session.commit()

    with pytest.raises(ValueError, match=r"already refunded|cannot refund"):
        TransactionService.process_refund(completed_sale.id, "Second refund attempt", test_user.id)


# ── Test Case J: Cannot Refund a Refund ──────────────────────────────────


def test_refund_of_refund_fails(db_session, test_user):
    """Cannot refund a transaction that is itself a refund."""
    refund_sale = Sale(
        document_number=f"REF-REFREF-{_counter}",
        date=datetime.now(),
        total_amount=-100.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=-100,
        payment_method="REFUND",
    )
    db_session.add(refund_sale)
    db_session.commit()

    with pytest.raises(ValueError, match="refund transaction"):
        TransactionService.process_refund(refund_sale.id, "Meta refund", test_user.id)


# ── Test Case K: Refund Non-existent Sale ────────────────────────────────


def test_refund_nonexistent_sale(db_session):
    """Refunding a non-existent sale raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        TransactionService.process_refund(999999, "Ghost sale", 1)


# ── Test Case L: B2B customers additionally get an A4 Tax Invoice ───────


def test_b2b_sale_hands_the_receipt_its_vat_customer(db_session, test_user, test_product, peripherals):
    """A VAT-registered customer's sale reaches the peripherals with the customer loaded,
    so the receipt and the A4 Tax Invoice can be printed after the session has closed."""
    customer = Customer(name="Registered Co", vat_number="VAT-12345")
    db_session.add(customer)
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        result = TransactionService.process_sale(cart_service, payments, customer_id=customer.id)

    (event,) = peripherals.events
    assert event.sale is result
    assert event.sale.customer.vat_number == "VAT-12345"


def test_walkin_sale_reaches_the_peripherals_without_a_customer(db_session, test_user, test_product, peripherals):
    """A walk-in (no customer) sale goes through the same single sale event."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        result = TransactionService.process_sale(cart_service, payments)

    (event,) = peripherals.events
    assert event.sale is result
    assert event.sale.customer is None


def test_issue_854_quick_pay_counts_as_cash(db_session, test_user, test_product):
    """Calling process_sale with the default cash method (as quick_pay does) counts in shift cash sales."""
    from cbpos.core.services.payment_service import PaymentService
    from cbpos.core.services.shift_service import ShiftService

    db_session.commit()

    shift_service = ShiftService()
    shift = shift_service.start_shift(test_user.id, Decimal("500.00"))

    cash_method = PaymentService.get_default_cash_method()
    assert cash_method is not None

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": cash_method.name, "amount": Decimal("200.00")}]

        sale = TransactionService.process_sale(cart_service, payments)

    assert sale is not None
    summary = shift_service.get_shift_summary(shift.id)
    assert summary["cash_sales"] == Decimal("200.00")
    assert summary["expected_cash"] == Decimal("700.00")


def test_issue_834_cash_overtender_stores_applied_amount(db_session, test_user, test_product):
    """Cash overtender stores applied amount on amount, original on tendered_amount, and shift cash is uninflated."""
    from cbpos.core.services.shift_service import ShiftService

    db_session.commit()
    shift_service = ShiftService()
    shift = shift_service.start_shift(test_user.id, Decimal("500.00"))

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("1.0"))  # price is 100.00
        payments = [{"method": "Cash", "amount": Decimal("1000.00")}]

        sale = TransactionService.process_sale(cart_service, payments)

    assert sale is not None
    assert len(sale.payments) == 1
    payment = sale.payments[0]
    assert payment.amount == Decimal("100.00")
    assert payment.tendered_amount == Decimal("1000.00")

    summary = shift_service.get_shift_summary(shift.id)
    assert summary["cash_sales"] == Decimal("100.00")
    assert summary["expected_cash"] == Decimal("600.00")  # starting 500 + 100 applied


def test_issue_834_split_cash_and_card_overtender_reduces_cash(db_session, test_user, test_product):
    """Split card and cash where cash overtenders reduces cash applied amount down to remaining due."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("1.0"))  # price is 100.00
        payments = [
            {"method": "Card", "amount": Decimal("60.00")},
            {"method": "Cash", "amount": Decimal("100.00")},
        ]

        sale = TransactionService.process_sale(cart_service, payments)

    assert sale is not None
    pmts = {p.payment_method: p for p in sale.payments}
    assert pmts["Card"].amount == Decimal("60.00")
    assert pmts["Card"].tendered_amount is None
    assert pmts["Cash"].amount == Decimal("40.00")
    assert pmts["Cash"].tendered_amount == Decimal("100.00")


def test_issue_834_receipt_shows_tendered_and_change(db_session, test_user, test_product):
    """Receipt commands include both tendered amount and change given."""
    from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder

    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("1.0"))  # price is 100.00
        payments = [{"method": "Cash", "amount": Decimal("1000.00")}]

        sale = TransactionService.process_sale(cart_service, payments)

    assert sale is not None
    assert sale.payments[0].amount == Decimal("100.00")
    assert sale.payments[0].tendered_amount == Decimal("1000.00")

    commands = SalesReceiptBuilder.build_receipt(sale)
    texts = [cmd.get("val", "") for cmd in commands if cmd.get("type") == "text"]
    full_text = " ".join(texts)
    assert "1,000.00" in full_text or "1000.00" in full_text
    assert "900.00" in full_text


def test_issue_851_credit_overpay_rejected_by_service(db_session, test_user, test_product):
    """Service rejects non-cash overtender such as Credit > total due."""
    from cbpos.core.models import Customer

    customer = Customer(name="Credit Customer", credit_limit=Decimal("5000.00"))
    db_session.add(customer)
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("1.0"))  # price is 100.00
        payments = [{"method": "Credit", "amount": Decimal("1000.00")}]

        with pytest.raises(ValueError, match="non_cash_overpay"):
            TransactionService.process_sale(cart_service, payments, customer_id=customer.id)


def test_issue_887_two_credit_lines_one_ledger_row_equal_to_debt_change(db_session, test_user, test_product):
    """Two CREDIT lines on one sale raise debt by both and write one ledger row for the total credit."""
    from cbpos.core.models import Customer, CustomerLedgerEntry

    customer = Customer(name="Multi Credit Customer", credit_limit=Decimal("5000.00"), current_debt=Decimal("0.00"))
    db_session.add(customer)
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("10.0"))  # price is 100.00 -> total 1000.00
        payments = [
            {"method": "Credit", "amount": Decimal("400.00")},
            {"method": "Credit", "amount": Decimal("600.00")},
        ]
        sale = TransactionService.process_sale(cart_service, payments, customer_id=customer.id)

    assert sale is not None
    db_session.refresh(customer)
    assert customer.current_debt == Decimal("1000.00")

    ledger_entries = db_session.query(CustomerLedgerEntry).filter_by(reference_id=sale.id).all()
    assert len(ledger_entries) == 1
    assert ledger_entries[0].amount == Decimal("1000.00")
    assert ledger_entries[0].balance_after == Decimal("1000.00")


def test_issue_847_void_after_refund_refused(db_session, test_user, test_product):
    """Void on a refunded sale raises ValueError('sale_has_refund') and leaves state unchanged."""
    from cbpos.core.models import Customer
    from cbpos.core.services.config_service import ConfigService

    ConfigService.set("enable_loyalty", True)
    ConfigService.set("loyalty_points_ratio", 100)
    ConfigService.set("loyalty_point_value", "1.00")
    ConfigService.set("loyalty_minimum_redeem", 50)

    customer = Customer(
        name="Loyalty Void Test Cust",
        phone="0771234567",
        loyalty_points=300,
        current_debt=Decimal("0.00"),
    )
    db_session.add(customer)
    test_product.stock_qty = 50.0
    test_product.price = Decimal("1000.00")
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("1.0"))
        payments = [{"method": "Cash", "amount": Decimal("900.00")}]
        sale = TransactionService.process_sale(
            cart_service, payments, customer_id=customer.id, loyalty_points_redeemed=100
        )
        assert sale is not None

        db_session.refresh(customer)
        db_session.refresh(test_product)
        assert customer.loyalty_points == 209
        assert test_product.stock_qty == 49.0

        refund_sale = TransactionService.process_refund(
            original_sale_id=sale.id,
            refund_reason="Damaged item",
            user_id=test_user.id,
        )
        assert refund_sale is not None

        db_session.refresh(customer)
        db_session.refresh(test_product)
        assert customer.loyalty_points == 300
        assert test_product.stock_qty == 50.0

        with pytest.raises(ValueError, match="sale_has_refund"):
            TransactionService.void_sale(sale.id, test_user.id, reason="Customer cancelled")

        db_session.refresh(customer)
        db_session.refresh(test_product)
        assert customer.loyalty_points == 300
        assert test_product.stock_qty == 50.0


def test_issue_847_reverse_sale_points_idempotent_after_redemption_return(db_session, test_user, test_product):
    """reverse_sale_points called after redemption return does not deduct positive redemption points."""
    from cbpos.core.models import Customer
    from cbpos.core.services.config_service import ConfigService
    from cbpos.core.services.loyalty_service import LoyaltyService

    ConfigService.set("enable_loyalty", True)
    ConfigService.set("loyalty_points_ratio", 100)
    ConfigService.set("loyalty_point_value", "1.00")
    ConfigService.set("loyalty_minimum_redeem", 50)

    customer = Customer(name="Idempotent Loyalty Cust", phone="0779998888", loyalty_points=300)
    db_session.add(customer)
    test_product.stock_qty = 50.0
    test_product.price = Decimal("1000.00")
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("1.0"))
        payments = [{"method": "Cash", "amount": Decimal("900.00")}]
        sale = TransactionService.process_sale(
            cart_service, payments, customer_id=customer.id, loyalty_points_redeemed=100
        )
        assert sale is not None

        refund_sale = TransactionService.process_refund(
            original_sale_id=sale.id,
            refund_reason="Return item",
            user_id=test_user.id,
        )
        assert refund_sale is not None

        db_session.refresh(customer)
        assert customer.loyalty_points == 300

        # Second reversal attempt should be a no-op (return None)
        entry = LoyaltyService.reverse_sale_points(db_session, sale, reason="REFUND")
        assert entry is None

        db_session.refresh(customer)
        assert customer.loyalty_points == 300


def test_issue_848_void_of_refund_document_refused(db_session, test_user, test_product):
    """void_sale on a refund document raises ValueError('cannot_void_refund') and leaves stock/debt unchanged."""
    from cbpos.core.models import Customer

    customer = Customer(
        name="Refund Void Cust",
        credit_limit=Decimal("5000.00"),
        current_debt=Decimal("0.00"),
    )
    db_session.add(customer)
    test_product.stock_qty = 20.0
    test_product.price = Decimal("500.00")
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))  # total 1000.00
        payments = [{"method": "Credit", "amount": Decimal("1000.00")}]
        sale = TransactionService.process_sale(cart_service, payments, customer_id=customer.id)
        assert sale is not None

        db_session.refresh(customer)
        db_session.refresh(test_product)
        assert customer.current_debt == Decimal("1000.00")
        assert test_product.stock_qty == 18.0

        ok = TransactionService.process_refund(
            original_sale_id=sale.id,
            refund_reason="Wrong purchase",
            user_id=test_user.id,
        )
        assert ok is True

        refund_sale = db_session.query(Sale).filter_by(refund_of_sale_id=sale.id).first()
        assert refund_sale is not None

        db_session.refresh(customer)
        db_session.refresh(test_product)
        assert customer.current_debt == Decimal("0.00")
        assert test_product.stock_qty == 20.0

        # Attempt to void the refund sale
        with pytest.raises(ValueError, match="cannot_void_refund"):
            TransactionService.void_sale(refund_sale.id, test_user.id, reason="Accidental refund")

        db_session.refresh(customer)
        db_session.refresh(test_product)
        assert customer.current_debt == Decimal("0.00")
        assert test_product.stock_qty == 20.0


def test_issue_915_process_refund_on_refunded_sale_raises(db_session, test_user, test_product):
    """Calling process_refund on an already refunded sale propagates ValueError instead of returning False (#915)."""
    test_product.stock_qty = 10.0
    test_product.price = Decimal("100.00")
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(test_product, qty=Decimal("1.0"))
        sale = TransactionService.process_sale(cart, [{"method": "Cash", "amount": Decimal("100.00")}])
        assert sale is not None

        # First refund succeeds
        assert TransactionService.process_refund(sale.id, "Return", test_user.id) is True

        # Second refund must raise ValueError, not return False
        with pytest.raises(ValueError):
            TransactionService.process_refund(sale.id, "Return again", test_user.id)


def test_issue_892_operational_error_propagates(db_session, test_user, test_product):
    """Unexpected database error during sale must propagate out of process_sale (#892)."""
    from sqlalchemy.exc import OperationalError

    test_product.price = Decimal("100.00")
    test_product.cost = Decimal("50.00")
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(test_product, qty=Decimal("1.0"))
        payments = [{"method": "Cash", "amount": Decimal("100.00")}]

        with patch.object(
            TransactionService,
            "_execute_sale",
            side_effect=OperationalError("SELECT", {}, Exception("database locked")),
        ):
            with pytest.raises(OperationalError):
                TransactionService.process_sale(cart, payments)


def test_issue_855_service_item_sells_with_zero_stock(db_session, test_user):
    """A service product with stock 0 sells when allow_negative_stock=False, and stock stays 0 with no movements (#855)."""
    from cbpos.core.services.config_service import ConfigService

    service = Product(
        name_en="Labor Repair",
        price=Decimal("1500.00"),
        stock_qty=Decimal("0.0"),
        barcode="SRV-855",
        is_service=True,
    )
    db_session.add(service)
    db_session.commit()

    with (
        patch.object(
            ConfigService,
            "get",
            side_effect=lambda k, d=None: False if k == "allow_negative_stock" else ConfigService.get_all().get(k, d),
        ),
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
    ):
        cart = CartService()
        cart.add_item(service, qty=Decimal("1.0"))
        payments = [{"method": "Cash", "amount": Decimal("1500.00")}]

        sale = TransactionService.process_sale(cart, payments)
        assert sale is not None

        db_session.refresh(service)
        assert service.stock_qty == Decimal("0.0")

        movements = db_session.query(StockMovement).filter(StockMovement.product_id == service.id).all()
        assert len(movements) == 0


def test_issue_855_composite_service_component_skipped(db_session, test_user):
    """Composite with a service component (stock 0) and physical component (stock 5) sells when allow_negative_stock=False (#855)."""
    from cbpos.core.models import CompositeItem
    from cbpos.core.services.config_service import ConfigService

    physical = Product(
        name_en="Screen Part",
        price=Decimal("1000.00"),
        stock_qty=Decimal("5.0"),
        barcode="PRT-855",
        is_service=False,
    )
    service_comp = Product(
        name_en="Screen Install Labor",
        price=Decimal("500.00"),
        stock_qty=Decimal("0.0"),
        barcode="SRV-COMP-855",
        is_service=True,
    )
    package = Product(
        name_en="Screen Replacement Package",
        price=Decimal("1500.00"),
        stock_qty=Decimal("0.0"),
        barcode="PKG-855",
        is_service=False,
    )
    db_session.add_all([physical, service_comp, package])
    db_session.flush()

    c1 = CompositeItem(parent_product_id=package.id, child_product_id=physical.id, qty=Decimal("1.0"))
    c2 = CompositeItem(parent_product_id=package.id, child_product_id=service_comp.id, qty=Decimal("1.0"))
    db_session.add_all([c1, c2])
    db_session.commit()

    with (
        patch.object(
            ConfigService,
            "get",
            side_effect=lambda k, d=None: False if k == "allow_negative_stock" else ConfigService.get_all().get(k, d),
        ),
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
    ):
        cart = CartService()
        cart.add_item(package, qty=Decimal("1.0"))
        payments = [{"method": "Cash", "amount": Decimal("1500.00")}]

        sale = TransactionService.process_sale(cart, payments)
        assert sale is not None

        db_session.refresh(physical)
        db_session.refresh(service_comp)
        assert physical.stock_qty == Decimal("4.0")
        assert service_comp.stock_qty == Decimal("0.0")
