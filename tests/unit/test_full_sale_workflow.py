"""
Integration test — Full Sale Workflow (19.4).

End-to-end test: Cart → Payment → Sale Record → Stock Deduction → Tax Calculation.
Uses real database (in-memory SQLite) with all services collaborating.
"""

from decimal import Decimal
from unittest.mock import patch

from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.models import (
    Product,
    User,
    Role,
    Permission,
    Sale,
    SaleItem,
    SalePayment,
    StockMovement,
    Customer,
    CustomerLedgerEntry,
)


_counter = 0


def _setup_scenario(db_session):
    """Create a realistic test scenario: user, products, customer with unique identifiers."""
    global _counter
    _counter += 1
    suffix = str(_counter)

    permission = Permission(code=f"sale_int_{suffix}")
    role = Role(name=f"Cashier_Int_{suffix}", permissions=[permission])
    user = User(username=f"cashier_int_{suffix}", pin_hash="hash", role=role)

    product_a = Product(
        name_en="Rice 5kg", price=Decimal("850.00"), stock_qty=Decimal("50.000"), barcode=f"INT{suffix}A"
    )
    product_b = Product(
        name_en="Sugar 1kg", price=Decimal("220.00"), stock_qty=Decimal("30.000"), barcode=f"INT{suffix}B"
    )

    customer = Customer(
        name=f"Mr. Perera {suffix}",
        credit_limit=Decimal("10000.00"),
        current_debt=Decimal("0.00"),
        payment_terms=30,
    )

    db_session.add_all([permission, role, user, product_a, product_b, customer])
    db_session.commit()

    return user, product_a, product_b, customer


class TestFullSaleWorkflow:
    """End-to-end sale workflow: cart → payment → stock → tax → records."""

    def test_cash_sale_full_workflow(self, db_session):
        """Complete cash sale: 2 products, cash payment, stock deducted, tax calculated."""
        user, product_a, product_b, _ = _setup_scenario(db_session)

        # 1. Build Cart
        with patch(
            "cbpos.core.services.cart_service.PricingService.calculate_price",
            side_effect=lambda p, c=None: {
                "final_price": p.price,
                "original_price": p.price,
                "applied_rule": "Standard Price",
            },
        ):
            cart = CartService()
            cart.add_item(product_a, qty=Decimal("2.000"))  # 850 * 2 = 1700
            cart.add_item(product_b, qty=Decimal("3.000"))  # 220 * 3 = 660

        # Verify cart totals
        totals = cart.get_totals()
        assert totals["subtotal"] == Decimal("2360.00")
        assert totals["count"] == 2
        assert totals["item_count"] == Decimal("5.000")

        # 2. Process Sale
        payments = [{"method": "CASH", "amount": Decimal("2360.00")}]

        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
        ):
            result = TransactionService.process_sale(cart, payments)

        assert result is True

        # 3. Verify Sale Record
        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        assert sale is not None
        assert sale.total_amount == Decimal("2360.00")
        assert sale.payment_method == "CASH"
        assert sale.user_id == user.id
        assert sale.document_number.startswith("REC-")

        # 4. Verify Sale Items
        items = db_session.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
        assert len(items) == 2

        rice_item = next(i for i in items if i.product_id == product_a.id)
        assert rice_item.qty == Decimal("2.000")
        assert rice_item.unit_price == Decimal("850.00")

        sugar_item = next(i for i in items if i.product_id == product_b.id)
        assert sugar_item.qty == Decimal("3.000")
        assert sugar_item.unit_price == Decimal("220.00")

        # 5. Verify Payment Record
        payment = db_session.query(SalePayment).filter(SalePayment.sale_id == sale.id).first()
        assert payment is not None
        assert payment.payment_method == "CASH"
        assert payment.amount == Decimal("2360.00")

        # 6. Verify Stock Deduction
        db_session.refresh(product_a)
        db_session.refresh(product_b)
        assert product_a.stock_qty == Decimal("48.000")  # 50 - 2
        assert product_b.stock_qty == Decimal("27.000")  # 30 - 3

        # 7. Verify Stock Movements Created
        movements_a = (
            db_session.query(StockMovement)
            .filter(StockMovement.product_id == product_a.id, StockMovement.type == "SALE")
            .all()
        )
        assert len(movements_a) >= 1
        assert movements_a[-1].qty_change == Decimal("-2.000")

        # 8. Verify Tax Calculation on Sale
        assert sale.tax_vat is not None
        assert sale.tax_sscl is not None
        assert sale.net_revenue is not None
        # Verify tax math: vat + sscl + net = total
        tax_sum = sale.tax_vat + sale.tax_sscl + sale.net_revenue
        assert abs(tax_sum - sale.total_amount) <= Decimal("0.02")

    def test_credit_sale_with_ledger(self, db_session):
        """Credit sale: updates customer debt and creates ledger entry."""
        user, product_a, _, customer = _setup_scenario(db_session)

        with patch(
            "cbpos.core.services.cart_service.PricingService.calculate_price",
            side_effect=lambda p, c=None: {
                "final_price": p.price,
                "original_price": p.price,
                "applied_rule": "Standard Price",
            },
        ):
            cart = CartService()
            cart.add_item(product_a, qty=Decimal("1.000"))

        payments = [{"method": "CREDIT", "amount": Decimal("850.00")}]

        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
        ):
            result = TransactionService.process_sale(cart, payments, customer_id=customer.id)

        assert result is True

        # Verify customer debt increased
        db_session.refresh(customer)
        assert customer.current_debt == Decimal("850.00")

        # Verify ledger entry was created
        entries = (
            db_session.query(CustomerLedgerEntry)
            .filter(
                CustomerLedgerEntry.customer_id == customer.id,
                CustomerLedgerEntry.entry_type == "SALE",
            )
            .all()
        )
        assert len(entries) == 1
        assert entries[0].amount == Decimal("850.00")

    def test_split_payment_sale(self, db_session):
        """Split payment: partial cash + partial card."""
        user, product_a, _, _ = _setup_scenario(db_session)

        with patch(
            "cbpos.core.services.cart_service.PricingService.calculate_price",
            side_effect=lambda p, c=None: {
                "final_price": p.price,
                "original_price": p.price,
                "applied_rule": "Standard Price",
            },
        ):
            cart = CartService()
            cart.add_item(product_a, qty=Decimal("1.000"))

        # Split: 500 cash + 350 card = 850
        payments = [
            {"method": "CASH", "amount": Decimal("500.00")},
            {"method": "CARD", "amount": Decimal("350.00")},
        ]

        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
        ):
            result = TransactionService.process_sale(cart, payments)

        assert result is True

        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        assert sale.payment_method == "SPLIT"

        # Verify both payment records
        sale_payments = db_session.query(SalePayment).filter(SalePayment.sale_id == sale.id).all()
        assert len(sale_payments) == 2
        methods = {p.payment_method for p in sale_payments}
        assert methods == {"CASH", "CARD"}

    def test_sale_then_void_then_verify_stock(self, db_session):
        """Full cycle: sale deducts stock, void restores it."""
        user, product_a, _, _ = _setup_scenario(db_session)
        original_stock = product_a.stock_qty

        # Sale
        with patch(
            "cbpos.core.services.cart_service.PricingService.calculate_price",
            side_effect=lambda p, c=None: {
                "final_price": p.price,
                "original_price": p.price,
                "applied_rule": "Standard Price",
            },
        ):
            cart = CartService()
            cart.add_item(product_a, qty=Decimal("5.000"))

        payments = [{"method": "CASH", "amount": Decimal("4250.00")}]

        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
        ):
            TransactionService.process_sale(cart, payments)

        db_session.refresh(product_a)
        assert product_a.stock_qty == original_stock - Decimal("5.000")

        # Void
        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        TransactionService.void_sale(sale.id, user.id, "Customer cancelled")

        db_session.refresh(product_a)
        assert product_a.stock_qty == original_stock

        # Verify sale status
        db_session.refresh(sale)
        assert sale.status == "VOID"

    def test_sale_then_refund_cycle(self, db_session):
        """Full cycle: sale → refund creates negative sale and restores stock."""
        user, product_a, _, _ = _setup_scenario(db_session)
        original_stock = product_a.stock_qty

        # Sale
        with patch(
            "cbpos.core.services.cart_service.PricingService.calculate_price",
            side_effect=lambda p, c=None: {
                "final_price": p.price,
                "original_price": p.price,
                "applied_rule": "Standard Price",
            },
        ):
            cart = CartService()
            cart.add_item(product_a, qty=Decimal("3.000"))

        payments = [{"method": "CASH", "amount": Decimal("2550.00")}]

        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
        ):
            TransactionService.process_sale(cart, payments)

        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        db_session.refresh(product_a)
        assert product_a.stock_qty == original_stock - Decimal("3.000")

        # Refund
        with (
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
            patch("cbpos.core.services.transaction_service.ConfigService.get_all", return_value={"language": "en"}),
        ):
            result = TransactionService.process_refund(sale.id, "Defective goods", user.id)

        assert result is True

        # Stock restored
        db_session.refresh(product_a)
        assert product_a.stock_qty == original_stock

        # Refund sale exists
        refund = db_session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).first()
        assert refund is not None
        assert refund.total_amount == -sale.total_amount

    def test_insufficient_payment_rejected(self, db_session):
        """Payment less than total amount is rejected."""
        user, product_a, _, _ = _setup_scenario(db_session)

        with patch(
            "cbpos.core.services.cart_service.PricingService.calculate_price",
            side_effect=lambda p, c=None: {
                "final_price": p.price,
                "original_price": p.price,
                "applied_rule": "Standard Price",
            },
        ):
            cart = CartService()
            cart.add_item(product_a, qty=Decimal("1.000"))  # 850

        payments = [{"method": "CASH", "amount": Decimal("100.00")}]  # Not enough

        import pytest

        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
            pytest.raises(ValueError, match="Insufficient payment"),
        ):
            TransactionService.process_sale(cart, payments)

        # Stock should be unchanged
        db_session.refresh(product_a)
        assert product_a.stock_qty == Decimal("50.000")

    def test_credit_limit_exceeded_rejected(self, db_session):
        """Credit sale exceeding customer limit is rejected."""
        user, product_a, _, customer = _setup_scenario(db_session)

        # Set a low credit limit
        customer.credit_limit = Decimal("100.00")
        db_session.commit()

        with patch(
            "cbpos.core.services.cart_service.PricingService.calculate_price",
            side_effect=lambda p, c=None: {
                "final_price": p.price,
                "original_price": p.price,
                "applied_rule": "Standard Price",
            },
        ):
            cart = CartService()
            cart.add_item(product_a, qty=Decimal("1.000"))  # 850 > 100 limit

        payments = [{"method": "CREDIT", "amount": Decimal("850.00")}]

        import pytest

        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
            pytest.raises(ValueError, match="Credit limit exceeded"),
        ):
            TransactionService.process_sale(cart, payments, customer_id=customer.id)

    def test_tax_breakdown_accuracy(self, db_session):
        """Verify that tax breakdown on a saved sale matches TaxService calculation."""
        user, product_a, _, _ = _setup_scenario(db_session)

        with patch(
            "cbpos.core.services.cart_service.PricingService.calculate_price",
            side_effect=lambda p, c=None: {
                "final_price": p.price,
                "original_price": p.price,
                "applied_rule": "Standard Price",
            },
        ):
            cart = CartService()
            cart.add_item(product_a, qty=Decimal("1.000"))

        payments = [{"method": "CASH", "amount": Decimal("850.00")}]

        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
            patch("cbpos.core.services.transaction_service.PrintWorker"),
            patch("cbpos.core.services.transaction_service.ReceiptService"),
        ):
            TransactionService.process_sale(cart, payments)

        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()

        # Compare with independent TaxService calculation
        expected_taxes = TaxService.calculate_taxes(Decimal("850.00"))

        assert sale.tax_vat == expected_taxes["vat"]
        assert sale.tax_sscl == expected_taxes["sscl"]
        assert sale.net_revenue == expected_taxes["net"]
