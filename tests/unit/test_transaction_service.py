from decimal import Decimal
from unittest.mock import patch
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.models import Product, User, Role, Sale, Permission, SaleItem, StockMovement
from cbpos.core.services.cart_service import CartService
from datetime import datetime


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
    product = Product(name_en="Test Product Atomic", price=100.0, stock_qty=10.0, barcode="123_atomic")
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
    product = Product(name_en="Test Product Void", price=100.0, stock_qty=8.0, barcode="123_void")
    db_session.add_all([permission, role, user, product])
    db_session.commit()

    sale = Sale(
        document_number="REC-VOID-TEST",
        date=datetime.now(),
        total_amount=100.0,
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=100,
        payment_method="CASH",
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        qty=2.0,
        unit_price=100.0,
        original_price=100.0,
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


# --- Test Case D: Void — Double Void Prevention ---
def test_void_sale_already_voided(db_session):
    """Voiding an already-voided sale returns False."""
    permission = Permission(code="void_double")
    role = Role(name="Manager_VoidDouble", permissions=[permission])
    user = User(username="mgr_void_double", pin_hash="hash", role=role)
    product = Product(name_en="Product VoidDouble", price=50.0, stock_qty=20.0, barcode="VD001")
    db_session.add_all([permission, role, user, product])
    db_session.commit()

    sale = Sale(
        document_number="REC-VD-TEST",
        date=datetime.now(),
        total_amount=50.0,
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=50,
        payment_method="CASH",
        status="VOID",
    )
    db_session.add(sale)
    sale_item = SaleItem(
        sale_id=None,
        product_id=product.id,
        qty=1.0,
        unit_price=50.0,
        original_price=50.0,
        subtotal=50.0,
    )
    db_session.flush()
    sale_item.sale_id = sale.id
    db_session.add(sale_item)
    db_session.commit()

    result = TransactionService.void_sale(sale.id, user.id, "Accidental double void")
    assert result is False

    # Stock should be unchanged
    db_session.refresh(product)
    assert product.stock_qty == 20.0


# --- Test Case E: Void — Non-existent sale ---
def test_void_nonexistent_sale(db_session):
    """Voiding a non-existent sale ID returns False."""
    result = TransactionService.void_sale(999999, 1, "Does not exist")
    assert result is False


# --- Test Case F: Void — Stock Restoration Audit Trail ---
def test_void_creates_stock_movements(db_session):
    """Voiding a sale creates VOID stock movements to restore inventory."""
    permission = Permission(code="void_audit")
    role = Role(name="Manager_VoidAudit", permissions=[permission])
    user = User(username="mgr_void_audit", pin_hash="hash", role=role)
    product = Product(name_en="Product VoidAudit", price=100.0, stock_qty=5.0, barcode="VA001")
    db_session.add_all([permission, role, user, product])
    db_session.commit()

    sale = Sale(
        document_number="REC-VA-TEST",
        date=datetime.now(),
        total_amount=300.0,
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=300,
        payment_method="CASH",
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        qty=3.0,
        unit_price=100.0,
        original_price=100.0,
        subtotal=300.0,
    )
    db_session.add(sale_item)
    db_session.commit()

    result = TransactionService.void_sale(sale.id, user.id, "Customer changed mind")
    assert result is True

    # Verify VOID stock movement exists
    void_movements = (
        db_session.query(StockMovement)
        .filter(StockMovement.product_id == product.id, StockMovement.type == "VOID")
        .all()
    )
    assert len(void_movements) >= 1
    # The void movement should have positive qty_change (restoring stock)
    last_void = void_movements[-1]
    assert last_void.qty_change == Decimal("3")

    # Stock restored
    db_session.refresh(product)
    assert product.stock_qty == 8.0


# --- Test Case G: Refund — Full Refund Workflow ---
def test_process_refund(db_session):
    """Full refund creates a negative sale, restores stock, and links to original."""
    permission = Permission(code="refund_test")
    role = Role(name="Manager_Refund", permissions=[permission])
    user = User(username="mgr_refund", pin_hash="hash", role=role)
    product = Product(name_en="Product Refund", price=200.0, stock_qty=7.0, barcode="RF001")
    db_session.add_all([permission, role, user, product])
    db_session.commit()

    # Create original sale
    sale = Sale(
        document_number="REC-RF-ORIG",
        date=datetime.now(),
        total_amount=400.0,
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=400,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        qty=2.0,
        unit_price=200.0,
        original_price=200.0,
        subtotal=400.0,
    )
    db_session.add(sale_item)
    db_session.commit()

    with (
        patch("cbpos.core.services.transaction_service.PrintWorker"),
        patch("cbpos.core.services.transaction_service.ReceiptService"),
        patch("cbpos.core.services.transaction_service.ConfigService.get_all", return_value={"language": "en"}),
    ):
        result = TransactionService.process_refund(sale.id, "Defective item", user.id)

    assert result is True

    # Verify refund sale was created
    refund_sale = db_session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).first()
    assert refund_sale is not None
    assert refund_sale.total_amount == Decimal("-400")
    assert refund_sale.payment_method == "REFUND"
    assert refund_sale.document_number.startswith("REF-")

    # Verify refund items have negative quantities
    refund_items = db_session.query(SaleItem).filter(SaleItem.sale_id == refund_sale.id).all()
    assert len(refund_items) == 1
    assert refund_items[0].qty == Decimal("-2")

    # Verify stock restored
    db_session.refresh(product)
    assert product.stock_qty == 9.0


# --- Test Case H: Refund — Cannot Refund Voided Sale ---
def test_refund_voided_sale_fails(db_session):
    """Cannot refund a sale that has been voided."""
    permission = Permission(code="refund_void")
    role = Role(name="Manager_RefVoid", permissions=[permission])
    user = User(username="mgr_refvoid", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.commit()

    sale = Sale(
        document_number="REC-RV-TEST",
        date=datetime.now(),
        total_amount=100.0,
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=100,
        payment_method="CASH",
        status="VOID",
    )
    db_session.add(sale)
    db_session.commit()

    with patch("cbpos.infrastructure.hardware.escpos_driver.PrintWorker"):
        result = TransactionService.process_refund(sale.id, "Should fail", user.id)

    assert result is False


# --- Test Case I: Refund — Cannot Double-Refund ---
def test_double_refund_fails(db_session):
    """Cannot refund a sale that has already been refunded."""
    permission = Permission(code="refund_double")
    role = Role(name="Manager_DblRef", permissions=[permission])
    user = User(username="mgr_dblref", pin_hash="hash", role=role)
    product = Product(name_en="Product DblRef", price=100.0, stock_qty=10.0, barcode="DR001")
    db_session.add_all([permission, role, user, product])
    db_session.commit()

    # Original sale
    original = Sale(
        document_number="REC-DR-ORIG",
        date=datetime.now(),
        total_amount=100.0,
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=100,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(original)
    db_session.flush()

    db_session.add(
        SaleItem(
            sale_id=original.id,
            product_id=product.id,
            qty=1.0,
            unit_price=100.0,
            original_price=100.0,
            subtotal=100.0,
        )
    )

    # Existing refund
    existing_refund = Sale(
        document_number="REF-DR-EXIST",
        date=datetime.now(),
        total_amount=-100.0,
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=-100,
        payment_method="REFUND",
        refund_of_sale_id=original.id,
    )
    db_session.add(existing_refund)
    db_session.commit()

    with patch("cbpos.infrastructure.hardware.escpos_driver.PrintWorker"):
        result = TransactionService.process_refund(original.id, "Second refund attempt", user.id)

    assert result is False


# --- Test Case J: Refund — Cannot Refund a Refund ---
def test_refund_of_refund_fails(db_session):
    """Cannot refund a transaction that is itself a refund."""
    permission = Permission(code="refund_ref")
    role = Role(name="Manager_RefRef", permissions=[permission])
    user = User(username="mgr_refref", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.commit()

    refund_sale = Sale(
        document_number="REF-REFREF",
        date=datetime.now(),
        total_amount=-100.0,
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=-100,
        payment_method="REFUND",
    )
    db_session.add(refund_sale)
    db_session.commit()

    with patch("cbpos.infrastructure.hardware.escpos_driver.PrintWorker"):
        result = TransactionService.process_refund(refund_sale.id, "Meta refund", user.id)

    assert result is False


# --- Test Case K: Refund — Non-existent sale ---
def test_refund_nonexistent_sale(db_session):
    """Refunding a non-existent sale returns False."""
    with patch("cbpos.infrastructure.hardware.escpos_driver.PrintWorker"):
        result = TransactionService.process_refund(999999, "Ghost sale", 1)
    assert result is False
