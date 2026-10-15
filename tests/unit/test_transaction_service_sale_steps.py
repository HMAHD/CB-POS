"""
Characterization tests for the sale branches of TransactionService (#732).

Pin what ``process_sale`` / ``void_sale`` / ``process_refund`` do today --
composite stock, weighted quantities, stock checks, credit, mixed payments and
the exempt amount -- so the sale transaction can be split into helpers without
any change a caller could see.
"""

import re
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import (
    Category,
    CompositeItem,
    Customer,
    CustomerLedgerEntry,
    Permission,
    Product,
    Role,
    Sale,
    SalePayment,
    StockMovement,
    User,
)
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


def _next() -> int:
    global _counter
    _counter += 1
    return _counter


def _list_price(product, customer=None):
    return {"final_price": product.price, "original_price": product.price, "applied_rule": "Standard Price"}


@pytest.fixture
def user(db_session):
    n = _next()
    permission = Permission(code=f"steps732_{n}")
    role = Role(name=f"Steps732Role_{n}", permissions=[permission])
    u = User(username=f"steps732_{n}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, u])
    db_session.flush()
    return u


def _product(db_session, name: str, price: str, stock: str) -> Product:
    p = Product(name_en=name, price=Decimal(price), stock_qty=Decimal(stock), barcode=f"732-{_next()}")
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def bundle(db_session):
    """A gift pack made of 2 x tea and 1 x biscuits; the pack itself holds no stock."""
    tea = _product(db_session, "Tea 100g", "300.00", "10")
    biscuits = _product(db_session, "Biscuits", "150.00", "5")
    pack = _product(db_session, "Gift Pack", "700.00", "0")
    db_session.add_all(
        [
            CompositeItem(parent_product_id=pack.id, child_product_id=tea.id, qty=Decimal("2")),
            CompositeItem(parent_product_id=pack.id, child_product_id=biscuits.id, qty=Decimal("1")),
        ]
    )
    db_session.flush()
    return pack, tea, biscuits


@pytest.fixture
def customer(db_session):
    c = Customer(name=f"Steps732 {_next()}", credit_limit=Decimal("5000.00"), current_debt=Decimal("100.00"))
    db_session.add(c)
    db_session.flush()
    return c


def _sell(db_session, user, lines, payments, customer_id=None):
    """Ring up ``lines`` [(product, qty)] paid by ``payments`` [(method, amount)]."""
    db_session.commit()
    with (
        patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_list_price),
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
    ):
        cart = CartService()
        for product, qty in lines:
            cart.add_item(product, qty=Decimal(qty))
        return TransactionService.process_sale(
            cart, [{"method": m, "amount": Decimal(a)} for m, a in payments], customer_id=customer_id
        )


def _stock(db_session, product) -> Decimal:
    db_session.refresh(product)
    return product.stock_qty


def _sale_count(db_session) -> int:
    return db_session.query(Sale).count()


# ── Composite products ───────────────────────────────────────────────────


class TestCompositeSale:
    def test_sale_takes_stock_from_the_components_not_the_pack(self, db_session, user, bundle):
        pack, tea, biscuits = bundle

        sale = _sell(db_session, user, [(pack, "2")], [("CASH", "1400.00")])

        assert sale is not None
        assert _stock(db_session, tea) == Decimal("6")  # 10 - 2 packs x 2
        assert _stock(db_session, biscuits) == Decimal("3")  # 5 - 2 packs x 1
        assert _stock(db_session, pack) == Decimal("0")

    def test_short_component_rejects_the_sale_and_writes_nothing(self, db_session, user, bundle):
        pack, tea, biscuits = bundle
        sales_before = _sale_count(db_session)

        with pytest.raises(ValueError, match="Insufficient stock for component 'Tea 100g' \\(in Gift Pack\\)"):
            _sell(db_session, user, [(pack, "6")], [("CASH", "4200.00")])

        assert _sale_count(db_session) == sales_before
        assert _stock(db_session, tea) == Decimal("10")
        assert _stock(db_session, biscuits) == Decimal("5")

    def test_void_puts_the_components_back(self, db_session, user, bundle):
        pack, tea, biscuits = bundle
        sale = _sell(db_session, user, [(pack, "2")], [("CASH", "1400.00")])

        assert TransactionService.void_sale(sale.id, user.id, "Wrong item") is True

        assert _stock(db_session, tea) == Decimal("10")
        assert _stock(db_session, biscuits) == Decimal("5")
        void_moves = db_session.query(StockMovement).filter_by(document_id=sale.id, type="VOID").all()
        assert sorted((m.product_id, m.qty_change) for m in void_moves) == sorted(
            [(tea.id, Decimal("4")), (biscuits.id, Decimal("2"))]
        )

    def test_refund_puts_the_components_back(self, db_session, user, bundle):
        pack, tea, biscuits = bundle
        sale = _sell(db_session, user, [(pack, "1")], [("CASH", "700.00")])

        with patch("cbpos.core.services.transaction_service.PrinterService"):
            assert TransactionService.process_refund(sale.id, "Damaged", user.id) is True

        assert _stock(db_session, tea) == Decimal("10")
        assert _stock(db_session, biscuits) == Decimal("5")
        refund = db_session.query(Sale).filter_by(refund_of_sale_id=sale.id).one()
        return_moves = db_session.query(StockMovement).filter_by(document_id=refund.id, type="RETURN").all()
        assert sorted((m.product_id, m.qty_change) for m in return_moves) == sorted(
            [(tea.id, Decimal("2")), (biscuits.id, Decimal("1"))]
        )


# ── Weighted quantities and plain stock checks ───────────────────────────


class TestStockCheck:
    def test_weighted_quantity_is_taken_to_three_decimals(self, db_session, user):
        dhal = _product(db_session, "Dhal (kg)", "400.00", "10.000")

        sale = _sell(db_session, user, [(dhal, "1.250")], [("CASH", "500.00")])

        assert _stock(db_session, dhal) == Decimal("8.750")
        (move,) = db_session.query(StockMovement).filter_by(document_id=sale.id, type="SALE").all()
        assert move.qty_change == Decimal("-1.250")
        assert sale.items[0].qty == Decimal("1.250")

    def test_short_stock_rejects_the_sale_and_writes_nothing(self, db_session, user):
        sugar = _product(db_session, "Sugar 1kg", "220.00", "2")
        sales_before = _sale_count(db_session)

        with pytest.raises(
            ValueError, match=re.escape("Insufficient stock for 'Sugar 1kg'. Available: 2.000, Required: 3")
        ):
            _sell(db_session, user, [(sugar, "3")], [("CASH", "660.00")])

        assert _sale_count(db_session) == sales_before
        assert _stock(db_session, sugar) == Decimal("2")

    def test_negative_stock_allowed_skips_the_check(self, db_session, user):
        sugar = _product(db_session, "Sugar 1kg", "220.00", "2")
        real_get = ConfigService.get

        real_get_all = ConfigService.get_all

        def allow_negative(key):
            return True if key == "allow_negative_stock" else real_get(key)

        def allow_negative_all():
            return {**real_get_all(), "allow_negative_stock": True}

        with (
            patch.object(ConfigService, "get", side_effect=allow_negative),
            patch.object(ConfigService, "get_all", side_effect=allow_negative_all),
        ):
            sale = _sell(db_session, user, [(sugar, "3")], [("CASH", "660.00")])

        assert sale is not None
        assert _stock(db_session, sugar) == Decimal("-1")

    def test_no_cashier_signed_in_rejects_the_sale(self, db_session, user):
        sugar = _product(db_session, "Sugar 1kg", "220.00", "5")

        with pytest.raises(ValueError, match=re.escape("No user logged in.")):
            _sell(db_session, None, [(sugar, "1")], [("CASH", "220.00")])

        assert _stock(db_session, sugar) == Decimal("5")


# ── Credit and mixed payments ────────────────────────────────────────────


class TestCreditAndMixedPayments:
    def test_cash_and_credit_split_charges_only_the_credit_part(self, db_session, user, customer):
        rice = _product(db_session, "Rice 5kg", "850.00", "10")

        sale = _sell(db_session, user, [(rice, "1")], [("CASH", "350.00"), ("CREDIT", "500.00")], customer.id)

        assert sale.payment_method == "SPLIT"
        payments = db_session.query(SalePayment).filter_by(sale_id=sale.id).all()
        assert sorted((p.payment_method, p.amount) for p in payments) == [
            ("CASH", Decimal("350.00")),
            ("CREDIT", Decimal("500.00")),
        ]
        db_session.refresh(customer)
        assert customer.current_debt == Decimal("600.00")
        (entry,) = db_session.query(CustomerLedgerEntry).filter_by(reference_id=sale.id).all()
        assert entry.amount == Decimal("500.00")
        assert entry.balance_after == Decimal("600.00")
        assert entry.reference_doc == sale.document_number
        assert sale.customer.id == customer.id

    def test_credit_without_a_customer_is_rejected(self, db_session, user):
        rice = _product(db_session, "Rice 5kg", "850.00", "10")

        with pytest.raises(ValueError, match=re.escape("Customer required for Credit sale.")):
            _sell(db_session, user, [(rice, "1")], [("CREDIT", "850.00")])

        assert _stock(db_session, rice) == Decimal("10")

    def test_credit_for_an_unknown_customer_is_rejected(self, db_session, user):
        rice = _product(db_session, "Rice 5kg", "850.00", "10")

        with pytest.raises(ValueError, match=re.escape("Invalid Customer.")):
            _sell(db_session, user, [(rice, "1")], [("CREDIT", "850.00")], customer_id=999_999)

    def test_credit_over_the_limit_leaves_the_debt_alone(self, db_session, user, customer):
        tv = _product(db_session, "TV", "6000.00", "3")

        with pytest.raises(ValueError, match="Credit limit exceeded"):
            _sell(db_session, user, [(tv, "1")], [("CREDIT", "6000.00")], customer.id)

        db_session.refresh(customer)
        assert customer.current_debt == Decimal("100.00")
        assert _stock(db_session, tv) == Decimal("3")


# ── Exempt amount ────────────────────────────────────────────────────────


def _exempt_config(key):
    if key in ("item_tax_exemptions", "vat_registered"):
        return True
    return ConfigService.DEFAULTS.get(key)


def _exempt_config_all():
    return {**ConfigService.DEFAULTS, "item_tax_exemptions": True, "vat_registered": True, "tax_vat_rate": 18.0}


def test_returned_sale_carries_the_exempt_amount_for_the_receipt(db_session, user):
    category = Category(name=f"Exempt732_{_next()}", tax_exempt=True)
    db_session.add(category)
    db_session.flush()
    rice = Product(
        name_en="Rice exempt",
        barcode=f"732-{_next()}",
        price=Decimal("118.00"),
        stock_qty=Decimal("10"),
        category_id=category.id,
    )
    soap = _product(db_session, "Soap", "118.00", "10")
    db_session.add(rice)
    db_session.flush()

    with (
        patch.object(ConfigService, "get", side_effect=_exempt_config),
        patch.object(ConfigService, "get_all", side_effect=_exempt_config_all),
    ):
        sale = _sell(db_session, user, [(rice, "1"), (soap, "1")], [("CASH", "236.00")])

    assert sale._exempt_amount == Decimal("118.00")
    assert sale.tax_vat == Decimal("18.00")
