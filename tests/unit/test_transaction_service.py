from decimal import Decimal
from unittest.mock import patch
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.models import Product, User, Role, Sale, Permission
from cbpos.core.services.cart_service import CartService


# --- Test Case A: Atomic Commit (Sale + Stock) ---
def test_process_sale_atomic(db_session):
    """
    Test that sale processing is atomic:
    1. Stock is deducted.
    2. Sale is saved.
    3. If error occurs, everything is rolled back.
    """
    # Setup Data
    permission = Permission(code="sale_atomic")
    role = Role(name="Cashier_Atomic", permissions=[permission])
    user = User(username="cashier_atomic", pin_hash="hash", role=role)
    product = Product(
        name_en="Test Product Atomic", price=100.0, stock_qty=10.0, barcode="123_atomic"
    )
    db_session.add_all([permission, role, user, product])
    db_session.commit()

    # Mock AuthService to return our user
    with (
        patch(
            "cbpos.core.services.auth_service.AuthService.get_current_user",
            return_value=user,
        ),
        patch("cbpos.infrastructure.hardware.escpos_driver.PrintWorker"),
    ):

        # Setup Cart
        cart_service = CartService()
        cart_service.add_item(product, qty=Decimal("2.0"))

        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        # Execute
        result = TransactionService.process_sale(cart_service, payments)

        # Verify Success
        assert result is True

        # Verify Stock Deduction
        db_session.refresh(product)
        assert product.stock_qty == 8.0

        # Verify Sale Record
        # Verify Sale Record
        # Get last sale since we don't know the receipt number
        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        assert sale is not None
        assert sale.total_amount == 200.0
        assert sale.items[0].qty == 2.0


def test_process_sale_rollback_on_error(db_session):
    """
    Test that transaction rolls back on error.
    """
    # Setup Data
    permission = Permission(code="sale_rollback")
    role = Role(name="Cashier_Rollback", permissions=[permission])
    user = User(username="cashier_rollback", pin_hash="hash", role=role)
    product = Product(
        name_en="Test Product Rollback",
        price=100.0,
        stock_qty=10.0,
        barcode="123_rollback",
    )
    db_session.add_all([permission, role, user, product])
    db_session.commit()

    with (
        patch(
            "cbpos.core.services.auth_service.AuthService.get_current_user",
            return_value=user,
        ),
        patch("cbpos.infrastructure.hardware.escpos_driver.PrintWorker"),
    ):

        cart_service = CartService()
        cart_service.add_item(product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        # Force an error during commit or processing
        # We mock SaleItem constructor to raise error
        # Note: We must patch where it is imported/used
        with patch(
            "cbpos.core.services.transaction_service.SaleItem",
            side_effect=Exception("DB Error"),
        ):
            result = TransactionService.process_sale(cart_service, payments)

            assert result is False

            # Verify Stock is NOT deducted
            db_session.refresh(product)
            assert product.stock_qty == 10.0


# --- Test Case B: Backward Tax Verification ---
def test_calculate_taxes():
    """
    Test TaxService backward calculation.
    """
    amount = Decimal("1000.00")
    taxes = TaxService.calculate_taxes(amount)

    # Just verify keys exist and are Decimals
    assert "vat" in taxes
    assert "sscl" in taxes
    assert "net" in taxes
    assert isinstance(taxes["vat"], Decimal)


# --- Test Case C: Hold/Void Integrity ---
def test_void_sale(db_session):
    """
    Test Void Sale functionality.
    """
    # Setup Sale
    permission = Permission(code="void_sale_unique")
    role = Role(name="Manager_Void", permissions=[permission])
    user = User(username="manager_void", pin_hash="hash", role=role)
    product = Product(
        name_en="Test Product Void", price=100.0, stock_qty=8.0, barcode="123_void"
    )
    db_session.add_all([permission, role, user, product])
    db_session.commit()

    sale = Sale(
        receipt_no="REC-VOID-TEST",
        total_amount=100.0,
        cashier_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=100,
        payment_method="CASH",
    )
    db_session.add(sale)
    db_session.flush()

    from cbpos.core.models import SaleItem

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        qty=2.0,
        unit_price=100.0,
        subtotal=200.0,
    )
    db_session.add(sale_item)
    db_session.commit()

    # Execute Void
    result = TransactionService.void_sale(sale.id, user.id, "Wrong Entry")

    assert result is True

    # Verify Status
    db_session.refresh(sale)
    assert sale.status == "VOID"

    # Verify Stock Return
    db_session.refresh(product)
    assert product.stock_qty == 10.0
