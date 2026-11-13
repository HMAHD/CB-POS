"""Domain tests for Warranty W3 (#823): Serial/IMEI capture at checkout,
cart serial bookkeeping, policy coupling, validation guards, and per-unit serial assignment.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import PaymentMethodKind
from cbpos.core.models import (
    AuditLog,
    PaymentMethod,
    Permission,
    Product,
    Role,
    User,
    WarrantyPolicy,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.core.utils.validators import validate_imei_luhn


def _create_user_with_permissions(db_session, username: str, perms: list[str]) -> User:
    role = Role(name=f"Role_{username}")
    db_session.add(role)
    db_session.flush()

    for code in perms:
        perm = db_session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if not perm:
            perm = Permission(code=code, description=code, group="Warranty")
            db_session.add(perm)
            db_session.flush()
        role.permissions.append(perm)

    user = User(username=username, pin_hash=AuthService.hash_pin("1234"), role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def policy_and_user(db_session):
    ConfigService.set("warranty_enabled", True)
    user = _create_user_with_permissions(
        db_session,
        "warr_serial_admin",
        [
            Permissions.WARRANTY_VIEW,
            Permissions.WARRANTY_EDIT,
            Permissions.WARRANTY_MANAGE_POLICIES,
            Permissions.INVENTORY_EDIT,
            Permissions.SALES_VIEW,
            Permissions.SALES_ADD_ITEM,
        ],
    )

    policy = WarrantyPolicy(
        name="Phone 1Y Shop Warranty",
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        provider_name="Colombo Tech Care",
        terms_text="Standard hardware warranty.",
        is_active=True,
    )
    db_session.add(policy)

    cash = PaymentMethod(name="CASH", kind=PaymentMethodKind.CASH, is_active=True)
    db_session.add(cash)
    db_session.commit()

    return {"user": user, "policy": policy, "cash": cash}


class TestImeiLuhnValidator:
    """Advisory Luhn check for 15-digit IMEI strings."""

    def test_valid_15_digit_imei(self):
        # 490154203237518 is a known valid Luhn IMEI
        assert validate_imei_luhn("490154203237518") is True

    def test_invalid_15_digit_imei(self):
        # Last digit changed from 8 to 9 -> fails Luhn
        assert validate_imei_luhn("490154203237519") is False

    def test_non_15_digit_or_alphanumeric_bypasses_luhn(self):
        # Alphanumeric laptop serial or short/long barcode bypasses without warning
        assert validate_imei_luhn("PF234XYZ") is True
        assert validate_imei_luhn("123456789") is True
        assert validate_imei_luhn("") is True
        assert validate_imei_luhn(None) is True


class TestCartServiceSerialBookkeeping:
    """Cart line serial slots, normalization, duplicate prevention, and reduction."""

    def test_cart_serial_slots_allocation(self, db_session, policy_and_user):
        product = Product(
            name_en="Pixel 8",
            price=Decimal("150000.00"),
            stock_qty=Decimal("10.0"),
            barcode="PIXEL8-01",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add(product)
        db_session.commit()

        cart = CartService()
        cart.add_item(product, Decimal("2"))

        assert len(cart.items) == 1
        item = cart.items[0]
        assert "serials" in item
        assert item["serials"] == [None, None]

    def test_cart_serial_normalization_and_uniqueness(self, db_session, policy_and_user):
        product1 = Product(
            name_en="Phone A",
            price=Decimal("50000.00"),
            stock_qty=Decimal("10.0"),
            barcode="PH-A",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        product2 = Product(
            name_en="Phone B",
            price=Decimal("60000.00"),
            stock_qty=Decimal("10.0"),
            barcode="PH-B",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add_all([product1, product2])
        db_session.commit()

        cart = CartService()
        cart.add_item(product1, Decimal("2"))
        cart.add_item(product2, Decimal("1"))

        # Set and normalize serials on line 0
        cart.set_item_serials(0, ["  sn-001 ", "sn-002  "])
        assert cart.items[0]["serials"] == ["SN-001", "SN-002"]

        # Duplicate serial within same line rejected
        with pytest.raises(ValueError, match=r"[Dd]uplicate"):
            cart.set_item_serials(0, ["SN-DUPE", "SN-DUPE"])

        # Duplicate serial across lines rejected
        with pytest.raises(ValueError, match=r"[Dd]uplicate"):
            cart.set_item_serials(1, ["SN-001"])

        # Non-duplicate on line 1 accepted
        cart.set_item_serials(1, ["SN-003"])
        assert cart.get_all_cart_serials() == {"SN-001", "SN-002", "SN-003"}

    def test_cart_merge_preserves_existing_serials(self, db_session, policy_and_user):
        product = Product(
            name_en="Pixel 8",
            price=Decimal("150000.00"),
            stock_qty=Decimal("10.0"),
            barcode="PIXEL8-02",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add(product)
        db_session.commit()

        cart = CartService()
        cart.add_item(product, Decimal("1"))
        cart.set_item_serials(0, ["SN-P1"])

        # Re-add same product with 1 more unit
        cart.add_item(product, Decimal("1"))
        assert len(cart.items) == 1
        assert cart.items[0]["qty"] == Decimal("2")
        assert cart.items[0]["serials"] == ["SN-P1", None]

    def test_cart_would_discard_serials_and_update_quantity(self, db_session, policy_and_user):
        product = Product(
            name_en="Pixel 8",
            price=Decimal("150000.00"),
            stock_qty=Decimal("10.0"),
            barcode="PIXEL8-03",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add(product)
        db_session.commit()

        cart = CartService()
        cart.add_item(product, Decimal("3"))
        cart.set_item_serials(0, ["SN-1", "SN-2", "SN-3"])

        # Reducing to 2 would discard SN-3
        discarded = cart.would_discard_serials(0, Decimal("2"))
        assert discarded == ["SN-3"]

        # Reducing to 1 would discard SN-2 and SN-3
        discarded_two = cart.would_discard_serials(0, Decimal("1"))
        assert discarded_two == ["SN-2", "SN-3"]

        # Applying update_quantity trims from end
        cart.update_quantity(0, Decimal("2"))
        assert cart.items[0]["serials"] == ["SN-1", "SN-2"]


class TestSuspendedBillSerialPersistence:
    """Held carts serialize normalized serials and restore them upon recall."""

    def test_hold_and_recall_cart_with_serials(self, db_session, policy_and_user):
        product = Product(
            name_en="Galaxy S24",
            price=Decimal("200000.00"),
            stock_qty=Decimal("10.0"),
            barcode="S24-01",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add(product)
        db_session.commit()

        cart = CartService()
        cart.add_item(product, Decimal("2"))
        cart.set_item_serials(0, ["IMEI-001", "IMEI-002"])

        held_id = SuspendedTransactionService.hold_bill(cart, note="Test serial hold")
        assert held_id is not None

        new_cart = CartService()
        recall_res = SuspendedTransactionService.recall_bill(held_id, new_cart)
        assert recall_res.ok is True
        assert len(new_cart.items) == 1
        assert new_cart.items[0]["serials"] == ["IMEI-001", "IMEI-002"]


class TestActiveWarrantySerialLookup:
    """Historical active warranty lookup for advisory conflict warnings."""

    def test_find_active_warranties_by_serials(self, db_session, policy_and_user):
        product = Product(
            name_en="iPad Pro",
            price=Decimal("300000.00"),
            stock_qty=Decimal("10.0"),
            barcode="IPAD-01",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add(product)
        db_session.commit()

        with patch.object(AuthService, "get_current_user", return_value=policy_and_user["user"]):
            cart = CartService()
            cart.add_item(product, Decimal("1"))
            cart.set_item_serials(0, ["SERIAL-ACTIVE-01"])
            sale = TransactionService.process_sale(cart, [{"method": "CASH", "amount": Decimal("300000.00")}])
            assert sale is not None

            found = WarrantyService.find_active_warranties_by_serials(
                product_id=product.id,
                serials=["SERIAL-ACTIVE-01", "SERIAL-NEW-99"],
                session=db_session,
            )
            assert found == {"SERIAL-ACTIVE-01": sale.document_number}


class TestInventoryPolicyCoupling:
    """Serial tracking requires a resolved active warranty policy."""

    def test_serial_mode_requires_resolved_warranty_policy(self, db_session, policy_and_user):
        # Product with explicit NONE warranty cannot enable REQUIRED or OPTIONAL serial mode
        data = {
            "name_en": "Cable",
            "price": Decimal("1000.00"),
            "barcode": "CABLE-01",
            "warranty_override": "NONE",
            "serial_mode": "REQUIRED",
        }
        with pytest.raises(ValueError, match="policy"):
            InventoryService().create_product(data, user_id=policy_and_user["user"].id, session=db_session)

    def test_weighted_product_cannot_have_serial_mode(self, db_session, policy_and_user):
        data = {
            "name_en": "Apples",
            "price": Decimal("500.00"),
            "barcode": "APPLES-01",
            "is_weighted": True,
            "serial_mode": "OPTIONAL",
        }
        with pytest.raises(ValueError, match="Weighted"):
            InventoryService().create_product(data, user_id=policy_and_user["user"].id, session=db_session)

    def test_valid_serial_product_creates_audit_log(self, db_session, policy_and_user):
        data = {
            "name_en": "Monitor",
            "price": Decimal("40000.00"),
            "barcode": "MON-01",
            "warranty_override": "POLICY",
            "warranty_policy_id": policy_and_user["policy"].id,
            "serial_mode": "REQUIRED",
        }
        prod = InventoryService().create_product(data, user_id=policy_and_user["user"].id, session=db_session)
        assert prod.serial_mode == "REQUIRED"

        audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.event_type == WARRANTY_EVENT,
                AuditLog.action == "PRODUCT_WARRANTY_ASSIGNMENT",
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert audit is not None
        assert "REQUIRED" in audit.details


class TestTransactionServiceSerialEnforcement:
    """Service layer checkout guards and per-unit serial assignment."""

    def test_required_serials_missing_raises_value_error(self, db_session, policy_and_user):
        product = Product(
            name_en="Laptop",
            price=Decimal("250000.00"),
            stock_qty=Decimal("10.0"),
            barcode="LAP-01",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add(product)
        db_session.commit()

        cart = CartService()
        cart.add_item(product, Decimal("1"))
        # Serials left as [None]

        with patch.object(AuthService, "get_current_user", return_value=policy_and_user["user"]):
            with pytest.raises(ValueError, match=r"[Ss]erial"):
                TransactionService.process_sale(
                    cart,
                    [{"method": "CASH", "amount": Decimal("250000.00")}],
                )

    def test_checkout_assigns_serials_to_warranties_in_order(self, db_session, policy_and_user):
        product = Product(
            name_en="Router",
            price=Decimal("15000.00"),
            stock_qty=Decimal("10.0"),
            barcode="RTR-01",
            serial_mode="REQUIRED",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add(product)
        db_session.commit()

        cart = CartService()
        cart.add_item(product, Decimal("2"))
        cart.set_item_serials(0, ["RTR-SN-01", "RTR-SN-02"])

        with patch.object(AuthService, "get_current_user", return_value=policy_and_user["user"]):
            sale = TransactionService.process_sale(
                cart,
                [{"method": "CASH", "amount": Decimal("30000.00")}],
            )
            assert sale is not None
            assert len(sale.warranties) == 2
            w1, w2 = sorted(sale.warranties, key=lambda w: w.unit_index)
            assert w1.unit_index == 1
            assert w1.serial_number == "RTR-SN-01"
            assert w2.unit_index == 2
            assert w2.serial_number == "RTR-SN-02"

    def test_optional_serial_allows_blank_with_null_warranty_serial(self, db_session, policy_and_user):
        product = Product(
            name_en="Headphones",
            price=Decimal("8000.00"),
            stock_qty=Decimal("10.0"),
            barcode="HD-01",
            serial_mode="OPTIONAL",
            warranty_override="POLICY",
            warranty_policy_id=policy_and_user["policy"].id,
        )
        db_session.add(product)
        db_session.commit()

        cart = CartService()
        cart.add_item(product, Decimal("1"))
        # Blank optional serial

        with patch.object(AuthService, "get_current_user", return_value=policy_and_user["user"]):
            sale = TransactionService.process_sale(
                cart,
                [{"method": "CASH", "amount": Decimal("8000.00")}],
            )
            assert sale is not None
            assert len(sale.warranties) == 1
            assert sale.warranties[0].serial_number is None
