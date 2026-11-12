"""Domain tests for TaxInvoiceService (#814)."""

import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import (
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    User,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.tax_invoice_service import TaxInvoiceService
from cbpos.core.services.transaction_service import TransactionService


@pytest.fixture
def test_db(db_session: Session):
    """Setup standard config and seed data for tax invoice testing."""
    ConfigService.set("vat_registered", True)
    ConfigService.set("tax_vat_rate", 18.0)
    ConfigService.set("company_tax_id", "123456789")
    ConfigService.set("shop_name", "Test Lanka Stores")
    ConfigService.set("shop_address", "123 Galle Road, Colombo 03")
    ConfigService.set("shop_phone", "+94 11 234 5678")
    ConfigService.set("terminal_id", "MAIN-01")
    ConfigService.set("terminal_mode", "standalone")

    # Role & User with sales.tax_invoice
    role = Role(name="TaxAdmin", access_level=9)
    db_session.add(role)
    db_session.flush()

    perm_code = Permissions.SALES_TAX_INVOICE
    perm = db_session.query(Permission).filter_by(code=perm_code).first()
    if not perm:
        perm = Permission(code=perm_code, description="Tax Invoice", group="Sales")
        db_session.add(perm)
        db_session.flush()
    role.permissions.append(perm)

    user = User(username="tax_user", pin_hash=AuthService.hash_pin("1234"), role_id=role.id)
    db_session.add(user)
    db_session.commit()
    AuthService._current_user = user

    yield db_session


def _create_sample_sale(
    session: Session,
    days_ago: int = 0,
    subtotal: Decimal = Decimal("1000.00"),
    vat: Decimal = Decimal("180.00"),
    total: Decimal = Decimal("1180.00"),
    discount: Decimal = Decimal("0.00"),
    is_void: bool = False,
    is_refund: bool = False,
) -> Sale:
    user = session.query(User).filter_by(username="tax_user").first()
    product = Product(
        barcode=f"BC-{datetime.now().timestamp()}",
        name_en="Test Item 1",
        price=Decimal("500.00"),
        cost=Decimal("300.00"),
        stock_qty=Decimal("100.000"),
    )
    session.add(product)
    session.flush()

    status = DocumentStatus.VOID if is_void else DocumentStatus.COMPLETED
    doc_num = f"INV-{int(datetime.now().timestamp() * 1000)}"
    payment_method = "REFUND" if is_refund else "CASH"

    sale = Sale(
        document_number=doc_num,
        type="sale",
        date=datetime.now() - timedelta(days=days_ago),
        user_id=user.id,
        status=status,
        total_amount=total,
        tax_vat=vat,
        net_revenue=subtotal - discount,
        additional_discount_value=discount,
        payment_method=payment_method,
    )
    session.add(sale)
    session.flush()

    item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        qty=Decimal("2.000"),
        unit_price=Decimal("500.00"),
        original_price=Decimal("500.00"),
        subtotal=subtotal,
    )
    session.add(item)
    session.commit()
    return sale


def test_serial_format_and_locale_independence(test_db):
    """Verify serial format matches regex YYMMM_QQQQ_XXXXX and uses English uppercase months."""
    regex = r"^\d{2}[A-Z]{3}_[A-Z0-9]{1,15}_\d{5,}$"

    # Test all 12 months
    for month in range(1, 13):
        dt = datetime(2026, month, 15, 10, 30)
        serial = TaxInvoiceService.generate_serial(issued_at=dt, terminal_code="MAIN")
        assert re.match(regex, serial)
        assert serial.startswith("26")
        expected_months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        assert expected_months[month - 1] in serial

    # Monotonic incrementation
    dt = datetime(2027, 1, 1)
    s1 = TaxInvoiceService.generate_serial(issued_at=dt, terminal_code="TILL01")
    s2 = TaxInvoiceService.generate_serial(issued_at=dt, terminal_code="TILL01")
    assert s1 != s2
    assert s1.endswith("_00001")
    assert s2.endswith("_00002")


def test_eligibility_validation(test_db):
    """Test eligibility conditions: VAT active, terminal mode, sale status, 28-day window."""
    sale = _create_sample_sale(test_db, days_ago=5)

    # 1. Eligible sale
    ok, err = TaxInvoiceService.validate_eligibility(sale.id)
    assert ok is True
    assert err is None

    # 2. VAT not active
    ConfigService.set("vat_registered", False)
    ok, err = TaxInvoiceService.validate_eligibility(sale.id)
    assert ok is False
    assert err == "tax_invoice.error_vat_not_active"
    ConfigService.set("vat_registered", True)

    # 3. Terminal mode restriction (till in network mode cannot issue)
    ConfigService.set("terminal_mode", "terminal")
    ok, err = TaxInvoiceService.validate_eligibility(sale.id)
    assert ok is False
    assert err == "tax_invoice.network_mode_restriction"
    ConfigService.set("terminal_mode", "standalone")

    # 4. Sale older than 28 days
    old_sale = _create_sample_sale(test_db, days_ago=29)
    ok, err = TaxInvoiceService.validate_eligibility(old_sale.id)
    assert ok is False
    assert err == "tax_invoice.error_window_expired"

    # 5. Voided sale
    void_sale = _create_sample_sale(test_db, is_void=True)
    ok, err = TaxInvoiceService.validate_eligibility(void_sale.id)
    assert ok is False
    assert err == "tax_invoice.error_sale_void"

    # 6. Refund sale
    refund_sale = _create_sample_sale(test_db, is_refund=True)
    ok, err = TaxInvoiceService.validate_eligibility(refund_sale.id)
    assert ok is False
    assert err == "tax_invoice.error_cannot_issue_on_refund"


def test_buyer_details_validation(test_db):
    """Buyer TIN must be exactly 9 digits, name and address non-empty."""
    sale = _create_sample_sale(test_db)
    user = test_db.query(User).filter_by(username="tax_user").first()

    # Invalid TIN: 8 digits
    with pytest.raises(ValueError, match="invalid_tin"):
        TaxInvoiceService.issue_tax_invoice(
            sale.id,
            {"name": "Lanka Corp", "address": "Colombo", "tin": "12345678"},
            user_id=user.id,
        )

    # Invalid TIN: alphanumeric
    with pytest.raises(ValueError, match="invalid_tin"):
        TaxInvoiceService.issue_tax_invoice(
            sale.id,
            {"name": "Lanka Corp", "address": "Colombo", "tin": "12345678A"},
            user_id=user.id,
        )

    # Missing name
    with pytest.raises(ValueError, match="missing_buyer_details"):
        TaxInvoiceService.issue_tax_invoice(
            sale.id,
            {"name": "  ", "address": "Colombo", "tin": "123456789"},
            user_id=user.id,
        )


def test_issue_tax_invoice_and_snapshots(test_db):
    """Test issuance creates immutable snapshots, reconciles lines, and formats amount in words."""
    sale = _create_sample_sale(
        test_db,
        subtotal=Decimal("1000.00"),
        vat=Decimal("180.00"),
        total=Decimal("1180.00"),
    )
    user = test_db.query(User).filter_by(username="tax_user").first()

    buyer = {
        "name": "Acme Holdings (Pvt) Ltd",
        "address": "45 Nawam Mawatha, Colombo 02",
        "phone": "+94 11 987 6543",
        "tin": "987654321",
    }

    inv = TaxInvoiceService.issue_tax_invoice(sale.id, buyer, user_id=user.id)
    assert inv is not None
    assert inv.id is not None
    assert inv.serial.startswith("26")
    assert inv.buyer_name == "Acme Holdings (Pvt) Ltd"
    assert inv.buyer_tin == "987654321"
    assert inv.supplier_name == "Test Lanka Stores"
    assert inv.supplier_tin == "123456789"
    assert inv.total_amount == Decimal("1180.00")
    assert inv.net_amount == Decimal("1000.00")
    assert inv.tax_vat == Decimal("180.00")
    assert inv.amount_in_words == "One Thousand One Hundred Eighty Rupees Only"
    assert inv.print_count == 0
    assert inv.original_printed_at is None

    # Verify line snapshot
    assert len(inv.lines) == 1
    line = inv.lines[0]
    assert line.product_name_snapshot == "Test Item 1"
    assert line.quantity == Decimal("2.000")
    assert line.unit_price == Decimal("500.00")
    assert line.net_amount == Decimal("1000.00")
    assert line.vat_amount == Decimal("180.00")
    assert line.total_amount == Decimal("1180.00")

    # Mutation test: changing original product price/name does not change the snapshot
    product = test_db.query(Product).filter_by(name_en="Test Item 1").first()
    product.name_en = "Mutated Product"
    product.price = Decimal("9999.00")
    test_db.commit()

    reloaded_inv = TaxInvoiceService.get_tax_invoice_by_sale_id(sale.id)
    assert reloaded_inv.lines[0].product_name_snapshot == "Test Item 1"
    assert reloaded_inv.lines[0].unit_price == Decimal("500.00")


def test_idempotent_issuance(test_db):
    """Calling issue_tax_invoice multiple times returns the exact same record."""
    sale = _create_sample_sale(test_db)
    user = test_db.query(User).filter_by(username="tax_user").first()
    buyer = {"name": "Lanka Corp", "address": "Colombo", "tin": "111222333"}

    inv1 = TaxInvoiceService.issue_tax_invoice(sale.id, buyer, user_id=user.id)
    inv2 = TaxInvoiceService.issue_tax_invoice(sale.id, buyer, user_id=user.id)
    assert inv1.id == inv2.id
    assert inv1.serial == inv2.serial


def test_void_sale_prevented_when_tax_invoice_issued(test_db):
    """Under VAT Act Section 25, sales with tax invoices cannot be voided."""
    sale = _create_sample_sale(test_db)
    user = test_db.query(User).filter_by(username="tax_user").first()
    buyer = {"name": "Lanka Corp", "address": "Colombo", "tin": "111222333"}

    TaxInvoiceService.issue_tax_invoice(sale.id, buyer, user_id=user.id)

    with pytest.raises(ValueError, match="cannot_void_tax_invoice_sale"):
        TransactionService.void_sale(sale.id, user_id=user.id, reason="Customer cancel")


def test_record_print_lifecycle(test_db):
    """Verify original/copy marking lifecycle via record_print."""
    sale = _create_sample_sale(test_db)
    user = test_db.query(User).filter_by(username="tax_user").first()
    buyer = {"name": "Lanka Corp", "address": "Colombo", "tin": "111222333"}

    inv = TaxInvoiceService.issue_tax_invoice(sale.id, buyer, user_id=user.id)
    assert inv.print_count == 0
    assert inv.original_printed_at is None

    # First print
    inv = TaxInvoiceService.record_print(inv.id, user_id=user.id)
    assert inv.print_count == 1
    assert inv.original_printed_at is not None
    first_printed_at = inv.original_printed_at

    # Second print (reprint)
    inv = TaxInvoiceService.record_print(inv.id, user_id=user.id)
    assert inv.print_count == 2
    assert inv.original_printed_at == first_printed_at


def test_checkout_atomic_issuance(test_db):
    """Test process_sale with tax_invoice_details commits Sale and TaxInvoice in one transaction."""
    from cbpos.core.models import PaymentMethod
    from cbpos.core.services.cart_service import CartService

    # Ensure CASH payment method exists
    pm = test_db.query(PaymentMethod).filter_by(name="CASH").first()
    if not pm:
        test_db.add(PaymentMethod(name="CASH", kind="CASH", is_active=True))
        test_db.commit()

    product = Product(
        barcode=f"BC-ATOMIC-{datetime.now().timestamp()}",
        name_en="Atomic Item",
        price=Decimal("1000.00"),
        cost=Decimal("600.00"),
        stock_qty=Decimal("100.000"),
    )
    test_db.add(product)
    test_db.commit()

    cart = CartService()
    cart.add_item(product, qty=Decimal("1.000"))

    buyer = {
        "name": "Atomic Corp",
        "address": "Colombo 01",
        "tin": "123456789",
    }

    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "CASH", "amount": Decimal("1000.00")}],
        tax_invoice_details=buyer,
    )
    assert sale is not None

    inv = TaxInvoiceService.get_tax_invoice_by_sale_id(sale.id)
    assert inv is not None
    assert inv.buyer_name == "Atomic Corp"
    assert inv.total_amount == Decimal("1000.00")
