"""Unit and domain tests for paid extended-warranty plans (Issue #829, Phase 9.6)."""

from datetime import timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import (
    Category,
    Customer,
    Product,
    Role,
    SaleItem,
    User,
    Warranty,
    WarrantyPolicy,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.refund_service import RefundLineRequest, RefundService
from cbpos.core.services.stock_service import StockService
from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.warranty_service import WarrantyService


@pytest.fixture
def setup_warranty_data(db_session):
    """Seed categories, policies, products, and cashier user for testing."""
    # Enable warranty
    ConfigService.set("warranty_enabled", True)

    cat = Category(name="Electronics")
    db_session.add(cat)
    db_session.flush()

    # Base shop policy: 1 Year
    base_policy = WarrantyPolicy(
        name="1 Year Shop",
        warranty_type="SHOP",
        duration=1,
        duration_unit="YEARS",
        remedy="REPAIR_OR_REPLACE",
        is_active=True,
    )
    # Extended policy: 1 Year, AFTER_BASE
    ext_policy_after = WarrantyPolicy(
        name="+1 Year Extended (After)",
        warranty_type="EXTENDED",
        duration=1,
        duration_unit="YEARS",
        remedy="REPAIR_OR_REPLACE",
        extended_starts="AFTER_BASE",
        is_active=True,
    )
    # Extended policy: 2 Years, FROM_SALE
    ext_policy_from = WarrantyPolicy(
        name="+2 Years Extended (From Sale)",
        warranty_type="EXTENDED",
        duration=2,
        duration_unit="YEARS",
        remedy="REPAIR_OR_REPLACE",
        extended_starts="FROM_SALE",
        is_active=True,
    )
    db_session.add_all([base_policy, ext_policy_after, ext_policy_from])
    db_session.flush()

    # Phone product with base warranty
    phone = Product(
        barcode="PHONE-001",
        name_en="Smartphone X",
        price=Decimal("100000.00"),
        cost=Decimal("70000.00"),
        stock_qty=Decimal("10.000"),
        category_id=cat.id,
        warranty_policy_id=base_policy.id,
        warranty_override="POLICY",
        is_service=False,
    )
    # Laptop product without base warranty
    laptop_no_base = Product(
        barcode="LAPTOP-NO-BASE",
        name_en="Laptop Basic",
        price=Decimal("150000.00"),
        cost=Decimal("110000.00"),
        stock_qty=Decimal("5.000"),
        category_id=cat.id,
        warranty_override="NONE",
        is_service=False,
    )
    # Extended plan product (+1 Year After)
    plan_prod_after = Product(
        barcode="PLAN-EXT-1Y",
        name_en="Extended Warranty +1 Year",
        price=Decimal("5000.00"),
        cost=Decimal("0.00"),
        stock_qty=Decimal("0.000"),
        category_id=cat.id,
        is_service=True,
        is_warranty_plan=True,
        plan_policy_id=ext_policy_after.id,
    )
    # Extended plan product (+2 Years From Sale)
    plan_prod_from = Product(
        barcode="PLAN-EXT-2Y",
        name_en="Extended Warranty +2 Years From Sale",
        price=Decimal("9000.00"),
        cost=Decimal("0.00"),
        stock_qty=Decimal("0.000"),
        category_id=cat.id,
        is_service=True,
        is_warranty_plan=True,
        plan_policy_id=ext_policy_from.id,
    )
    # Customer
    customer = Customer(name="Akash Customer", phone="0771234567")

    # Cashier user & role
    role = Role(name="Cashier")
    db_session.add(role)
    db_session.flush()
    user = User(username="cashier_test", pin_hash="fake_hash", role_id=role.id, is_active=True)

    db_session.add_all([phone, laptop_no_base, plan_prod_after, plan_prod_from, customer, user])
    db_session.commit()

    old_user = AuthService.get_current_user()
    AuthService._current_user = user

    yield {
        "cat": cat,
        "base_policy": base_policy,
        "ext_policy_after": ext_policy_after,
        "ext_policy_from": ext_policy_from,
        "phone": phone,
        "laptop": laptop_no_base,
        "plan_after": plan_prod_after,
        "plan_from": plan_prod_from,
        "customer": customer,
        "user": user,
    }

    AuthService._current_user = old_user


def test_plan_product_rules(setup_warranty_data, db_session):
    """Test plan product invariants: is_service=True, policy type EXTENDED, no base warranty, no stock move."""
    data = setup_warranty_data
    plan = data["plan_after"]

    assert plan.is_warranty_plan is True
    assert plan.is_service is True
    assert plan.plan_policy.warranty_type == "EXTENDED"

    # Plan products never resolve base policies
    pol_map = WarrantyService.resolve_policies_for_products(db_session, [plan.id, data["phone"].id])
    assert pol_map[plan.id] is None
    assert pol_map[data["phone"].id] is not None

    # StockService skips stock movement for is_service
    res = StockService.record_movement(
        product_id=plan.id,
        qty_change=Decimal("-1.000"),
        movement_type="SALE",
        user_id=data["user"].id,
        session=db_session,
    )
    assert res is None


def test_cart_stable_linkage_and_quantities(setup_warranty_data):
    """Test cart line IDs, plan linkage, quantity clamps, and removal cascades."""
    data = setup_warranty_data
    cart = CartService()

    # Add 2 phones
    cart.add_item(data["phone"], qty=Decimal("2.000"))
    assert len(cart.items) == 1
    phone_line = cart.items[0]
    phone_line_id = phone_line["line_id"]
    assert phone_line_id is not None

    # Adding plan covering phone line
    cart.add_item(data["plan_after"], qty=Decimal("2.000"), covered_line_id=phone_line_id)
    assert len(cart.items) == 2
    plan_line = cart.items[1]
    assert plan_line.get("covered_line_id") == phone_line_id

    # Exceeding plan quantity should fail
    with pytest.raises(ValueError):
        cart.add_item(data["plan_after"], qty=Decimal("1.000"), covered_line_id=phone_line_id)

    # Exceeding plan quantity via update_quantity should fail
    with pytest.raises(ValueError):
        cart.update_quantity(1, Decimal("3.000"))

    # Reducing phone quantity to 1 should clamp plan quantity to 1 with translated notice
    notice = cart.update_quantity(0, Decimal("1.000"))
    assert cart.items[0]["qty"] == Decimal("1.000")
    assert cart.items[1]["qty"] == Decimal("1.000")
    assert notice is not None

    # Removing phone should remove linked plan line
    cart.remove_item(0)
    assert len(cart.items) == 0


def test_cart_merge_isolation(setup_warranty_data):
    """Test that plans for different lines never merge into each other."""
    data = setup_warranty_data
    cart = CartService()

    # Add 1 phone
    cart.add_item(data["phone"], qty=Decimal("1.000"))
    phone_line_id = cart.items[0]["line_id"]

    # Add 1 laptop
    cart.add_item(data["laptop"], qty=Decimal("1.000"))
    laptop_line_id = cart.items[1]["line_id"]

    # Add plan for phone
    cart.add_item(data["plan_after"], qty=Decimal("1.000"), covered_line_id=phone_line_id)

    # Add same plan for laptop
    cart.add_item(data["plan_after"], qty=Decimal("1.000"), covered_line_id=laptop_line_id)

    # Must be 4 distinct items in cart (no improper merge of plans)
    assert len(cart.items) == 4
    assert cart.items[2]["covered_line_id"] == phone_line_id
    assert cart.items[3]["covered_line_id"] == laptop_line_id


def test_held_bill_preserves_linkage(setup_warranty_data, db_session):
    """Test that suspended transactions retain line_id and covered_line_id across recall."""
    data = setup_warranty_data
    cart = CartService()
    cart.set_customer(data["customer"])

    cart.add_item(data["phone"], qty=Decimal("1.000"), serials=["SN-PHONE-01"])
    phone_line_id = cart.items[0]["line_id"]
    cart.add_item(data["plan_after"], qty=Decimal("1.000"), covered_line_id=phone_line_id)

    # Hold bill
    suspended_id = SuspendedTransactionService.hold_bill(cart, note="Test Held Bill")
    assert suspended_id is not None

    # Clear cart
    cart.clear()
    assert len(cart.items) == 0

    # Recall bill
    res = SuspendedTransactionService.recall_bill(suspended_id, cart)
    assert res.ok is True
    assert len(cart.items) == 2

    recalled_phone = cart.items[0]
    recalled_plan = cart.items[1]

    assert recalled_plan.get("covered_line_id") == recalled_phone.get("line_id")
    assert recalled_phone.get("serials") == ["SN-PHONE-01"]


def test_atomic_registration_after_base(setup_warranty_data, db_session):
    """Test selling 2 phones + 2 plans (AFTER_BASE): creates 2 base + 2 extended warranties chained."""
    data = setup_warranty_data
    cart = CartService()
    cart.set_customer(data["customer"])

    cart.add_item(data["phone"], qty=Decimal("2.000"), serials=["SN-P1", "SN-P2"])
    phone_line_id = cart.items[0]["line_id"]
    cart.add_item(data["plan_after"], qty=Decimal("2.000"), covered_line_id=phone_line_id)

    totals = cart.get_totals()
    payments = [{"method": "Cash", "amount": totals["final_total"]}]

    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=payments,
        customer_id=data["customer"].id,
    )

    assert sale is not None

    # Check sale items linkage
    items = db_session.query(SaleItem).filter(SaleItem.sale_id == sale.id).order_by(SaleItem.id).all()
    assert len(items) == 2
    phone_item = items[0]
    plan_item = items[1]
    assert plan_item.covered_item_id == phone_item.id

    # Check warranties created: 2 base + 2 extended
    warranties = db_session.query(Warranty).filter(Warranty.sale_id == sale.id).order_by(Warranty.id).all()
    assert len(warranties) == 4

    base_w1, base_w2, ext_w1, ext_w2 = warranties

    # Base warranties
    assert base_w1.warranty_type == "SHOP"
    assert base_w1.unit_index == 1
    assert base_w1.serial_number == "SN-P1"
    assert base_w1.covers_warranty_id is None

    assert base_w2.warranty_type == "SHOP"
    assert base_w2.unit_index == 2
    assert base_w2.serial_number == "SN-P2"
    assert base_w2.covers_warranty_id is None

    # Extended warranties (chained)
    assert ext_w1.warranty_type == "EXTENDED"
    assert ext_w1.unit_index == 1
    assert ext_w1.covers_warranty_id == base_w1.id
    assert ext_w1.plan_sale_item_id == plan_item.id
    assert ext_w1.product_id == data["phone"].id
    assert ext_w1.start_date == base_w1.end_date + timedelta(days=1)
    assert ext_w1.end_date == WarrantyService.compute_end_date(
        ext_w1.start_date, data["ext_policy_after"].duration, data["ext_policy_after"].duration_unit
    )

    assert ext_w2.warranty_type == "EXTENDED"
    assert ext_w2.unit_index == 2
    assert ext_w2.covers_warranty_id == base_w2.id
    assert ext_w2.plan_sale_item_id == plan_item.id
    assert ext_w2.product_id == data["phone"].id
    assert ext_w2.start_date == base_w2.end_date + timedelta(days=1)


def test_atomic_registration_from_sale_and_no_base(setup_warranty_data, db_session):
    """Test extended plan with FROM_SALE and on an item without base warranty."""
    data = setup_warranty_data
    cart = CartService()
    cart.set_customer(data["customer"])

    # Laptop has NO base warranty, covered with FROM_SALE plan
    cart.add_item(data["laptop"], qty=Decimal("1.000"))
    laptop_line_id = cart.items[0]["line_id"]
    cart.add_item(data["plan_from"], qty=Decimal("1.000"), covered_line_id=laptop_line_id)

    totals = cart.get_totals()
    payments = [{"method": "Cash", "amount": totals["final_total"]}]

    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=payments,
        customer_id=data["customer"].id,
    )

    assert sale is not None

    warranties = db_session.query(Warranty).filter(Warranty.sale_id == sale.id).all()
    # Exactly 1 warranty (the extended one) because laptop had no base policy
    assert len(warranties) == 1
    ext_w = warranties[0]
    assert ext_w.warranty_type == "EXTENDED"
    assert ext_w.covers_warranty_id is None
    assert ext_w.start_date == sale.date.date()


def test_void_sale_cascades_to_all_warranties(setup_warranty_data, db_session):
    """Voiding a sale marks both base and extended warranties VOID."""
    data = setup_warranty_data
    cart = CartService()
    cart.add_item(data["phone"], qty=Decimal("1.000"))
    phone_line_id = cart.items[0]["line_id"]
    cart.add_item(data["plan_after"], qty=Decimal("1.000"), covered_line_id=phone_line_id)

    totals = cart.get_totals()
    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "Cash", "amount": totals["final_total"]}],
    )

    # Void the sale
    TransactionService.void_sale(sale.id, user_id=data["user"].id, reason="Customer changed mind")

    warranties = db_session.query(Warranty).filter(Warranty.sale_id == sale.id).all()
    assert len(warranties) == 2
    for w in warranties:
        assert w.status == "VOID"


def test_refund_plan_line_alone(setup_warranty_data, db_session):
    """Refunding only the plan line cancels the extended warranty; base warranty stays ACTIVE."""
    data = setup_warranty_data
    cart = CartService()
    cart.add_item(data["phone"], qty=Decimal("1.000"))
    phone_line_id = cart.items[0]["line_id"]
    cart.add_item(data["plan_after"], qty=Decimal("1.000"), covered_line_id=phone_line_id)

    totals = cart.get_totals()
    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "Cash", "amount": totals["final_total"]}],
    )

    items = db_session.query(SaleItem).filter(SaleItem.sale_id == sale.id).order_by(SaleItem.id).all()
    plan_item = items[1]

    # Refund only plan line
    res = RefundService.refund(
        sale_id=sale.id,
        lines=[RefundLineRequest(sale_item_id=plan_item.id, qty=Decimal("1.000"), reason="Cancel plan")],
        user_id=data["user"].id,
        reason="Plan return",
    )
    assert res is not None

    warranties = db_session.query(Warranty).filter(Warranty.sale_id == sale.id).order_by(Warranty.id).all()
    base_w, ext_w = warranties

    assert base_w.status == "ACTIVE"
    assert ext_w.status == "CANCELLED"


def test_refund_base_unit_cancels_extended_warranty(setup_warranty_data, db_session):
    """Refunding base unit cancels both base warranty and linked extended warranty."""
    data = setup_warranty_data
    cart = CartService()
    cart.add_item(data["phone"], qty=Decimal("1.000"))
    phone_line_id = cart.items[0]["line_id"]
    cart.add_item(data["plan_after"], qty=Decimal("1.000"), covered_line_id=phone_line_id)

    totals = cart.get_totals()
    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "Cash", "amount": totals["final_total"]}],
    )

    items = db_session.query(SaleItem).filter(SaleItem.sale_id == sale.id).order_by(SaleItem.id).all()
    phone_item = items[0]

    # Refund base phone unit
    res = RefundService.refund(
        sale_id=sale.id,
        lines=[RefundLineRequest(sale_item_id=phone_item.id, qty=Decimal("1.000"), reason="Defective phone")],
        user_id=data["user"].id,
        reason="Phone return",
    )
    assert res is not None

    warranties = db_session.query(Warranty).filter(Warranty.sale_id == sale.id).order_by(Warranty.id).all()
    base_w, ext_w = warranties

    assert base_w.status == "CANCELLED"
    assert ext_w.status == "CANCELLED"


def test_serial_selected_refund_cancels_exact_chain(setup_warranty_data, db_session):
    """Serial-selected refund cancels exactly the base unit with that serial and its linked extended warranty."""
    data = setup_warranty_data
    cart = CartService()
    cart.add_item(data["phone"], qty=Decimal("2.000"), serials=["SN-ALPHA", "SN-BETA"])
    phone_line_id = cart.items[0]["line_id"]
    cart.add_item(data["plan_after"], qty=Decimal("2.000"), covered_line_id=phone_line_id)

    totals = cart.get_totals()
    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "Cash", "amount": totals["final_total"]}],
    )

    items = db_session.query(SaleItem).filter(SaleItem.sale_id == sale.id).order_by(SaleItem.id).all()
    phone_item = items[0]

    # Refund unit with SN-BETA
    RefundService.refund(
        sale_id=sale.id,
        lines=[
            RefundLineRequest(
                sale_item_id=phone_item.id, qty=Decimal("1.000"), reason="Return unit 2", selected_serials=["SN-BETA"]
            )
        ],
        user_id=data["user"].id,
        reason="Single unit return",
    )

    warranties = db_session.query(Warranty).filter(Warranty.sale_id == sale.id).order_by(Warranty.id).all()
    base_1, base_2, ext_1, ext_2 = warranties

    # Unit 1 (SN-ALPHA) remains active
    assert base_1.serial_number == "SN-ALPHA"
    assert base_1.status == "ACTIVE"
    assert ext_1.status == "ACTIVE"

    # Unit 2 (SN-BETA) and its linked extended warranty are cancelled
    assert base_2.serial_number == "SN-BETA"
    assert base_2.status == "CANCELLED"
    assert ext_2.covers_warranty_id == base_2.id
    assert ext_2.status == "CANCELLED"
