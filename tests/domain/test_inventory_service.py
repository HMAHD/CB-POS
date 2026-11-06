"""
InventoryService.adjust_stock() built an AuditLog row without event_type,
a non-nullable column -- session.commit() raised IntegrityError, which the
surrounding try/except only catches for StaleDataError, so it propagated
out uncaught. A stock adjustment could fail outright rather than merely
fail to log.
"""

from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.constants.status import MovementType
from cbpos.core.models import AuditLog, InventoryLog, Product, Role, StockMovement, User
from cbpos.core.services.inventory_service import InventoryService

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_product(db_session):
    suffix = _next_suffix()
    product = Product(
        barcode=f"BC{suffix}",
        name_en=f"Test Product {suffix}",
        price=Decimal("100.00"),
        stock_qty=Decimal("10"),
    )
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def test_user(db_session):
    suffix = _next_suffix()
    admin_role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
    if not admin_role:
        admin_role = Role(name=ADMIN_ROLE_NAME, access_level=9)
        db_session.add(admin_role)
        db_session.flush()
    user = User(username=f"user_{suffix}", pin_hash="hash", role_id=admin_role.id)
    db_session.add(user)
    db_session.flush()
    return user


class TestAdjustStock:
    def test_commits_successfully_and_records_both_logs(self, db_session, test_product, test_user):
        service = InventoryService()

        result = service.adjust_stock(
            product_id=test_product.id,
            qty_change=Decimal("5"),
            reason="Stock take correction",
            user_id=test_user.id,
        )

        assert bool(result) is True

        db_session.expire_all()
        refreshed = db_session.get(Product, test_product.id)
        assert refreshed.stock_qty == Decimal("15")

        inv_log = db_session.query(InventoryLog).filter_by(product_id=test_product.id).one()
        assert inv_log.qty_change == Decimal("5")

        audit_log = db_session.query(AuditLog).filter_by(action="STOCK_ADJUSTMENT").one()
        assert audit_log.event_type == "INVENTORY"
        assert audit_log.user_id == test_user.id

    def test_issue_794_adjust_stock_writes_movement_and_audit(self, db_session, test_product, test_user):
        """#794: adjust_stock writes a StockMovement(type=ADJUSTMENT) and updates stock atomically."""
        service = InventoryService()

        movement = service.adjust_stock(
            product_id=test_product.id,
            qty_change=Decimal("-2"),
            reason="DAMAGED",
            user_id=test_user.id,
            note="Broken bottle on shelf",
        )

        assert isinstance(movement, StockMovement)
        assert movement.type == MovementType.ADJUSTMENT
        assert movement.qty_change == Decimal("-2")
        assert movement.balance_after == Decimal("8")
        assert movement.product_id == test_product.id
        assert movement.user_id == test_user.id

        db_session.expire_all()
        refreshed = db_session.get(Product, test_product.id)
        assert refreshed.stock_qty == Decimal("8")

        # InventoryLog and AuditLog recorded
        inv_log = db_session.query(InventoryLog).filter_by(product_id=test_product.id).one()
        assert inv_log.qty_change == Decimal("-2")
        assert "DAMAGED" in inv_log.reason

        audit_log = db_session.query(AuditLog).filter_by(action="STOCK_ADJUSTMENT").one()
        assert audit_log.event_type == "INVENTORY"
        assert audit_log.user_id == test_user.id
        assert "DAMAGED" in audit_log.details
        assert "Broken bottle" in audit_log.details

    def test_issue_794_adjust_requires_permission(self, db_session, test_product):
        """#794: adjust_stock requires inventory.stock_adjust permission."""
        service = InventoryService()
        suffix = _next_suffix()
        cashier_role = Role(name=f"Cashier_{suffix}", access_level=1)
        db_session.add(cashier_role)
        db_session.flush()

        cashier = User(username=f"cashier_{suffix}", pin_hash="hash", role_id=cashier_role.id)
        db_session.add(cashier)
        db_session.flush()

        with pytest.raises(PermissionError, match=r"inventory\.stock_adjust"):
            service.adjust_stock(
                product_id=test_product.id,
                qty_change=Decimal("1"),
                reason="FOUND",
                user_id=cashier.id,
            )

    def test_issue_794_adjust_rejects_zero_and_service(self, db_session, test_user):
        """#794: adjust_stock rejects zero quantity change and service products."""
        service = InventoryService()
        suffix = _next_suffix()
        service_prod = Product(
            barcode=f"SRV{suffix}",
            name_en=f"Labor Service {suffix}",
            price=Decimal("500.00"),
            stock_qty=Decimal("0"),
            is_service=True,
        )
        norm_prod = Product(
            barcode=f"NRM{suffix}",
            name_en=f"Normal Item {suffix}",
            price=Decimal("100.00"),
            stock_qty=Decimal("10"),
        )
        db_session.add_all([service_prod, norm_prod])
        db_session.flush()

        # Reject qty_change == 0
        with pytest.raises(ValueError, match="zero"):
            service.adjust_stock(
                product_id=norm_prod.id,
                qty_change=Decimal("0"),
                reason="CORRECTION",
                user_id=test_user.id,
            )

        # Reject service product
        with pytest.raises(ValueError, match="service"):
            service.adjust_stock(
                product_id=service_prod.id,
                qty_change=Decimal("1"),
                reason="FOUND",
                user_id=test_user.id,
            )

        # Reject OTHER reason without note
        with pytest.raises(ValueError, match="note"):
            service.adjust_stock(
                product_id=norm_prod.id,
                qty_change=Decimal("1"),
                reason="OTHER",
                user_id=test_user.id,
                note="",
            )
