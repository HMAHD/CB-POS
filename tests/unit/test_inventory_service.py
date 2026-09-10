"""
InventoryService.adjust_stock() built an AuditLog row without event_type,
a non-nullable column -- session.commit() raised IntegrityError, which the
surrounding try/except only catches for StaleDataError, so it propagated
out uncaught. A stock adjustment could fail outright rather than merely
fail to log.
"""

import pytest
from decimal import Decimal

from cbpos.core.models import AuditLog, InventoryLog, Product, User
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
    user = User(username=f"user_{suffix}", pin_hash="hash")
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

        assert result is True

        db_session.expire_all()
        refreshed = db_session.get(Product, test_product.id)
        assert refreshed.stock_qty == Decimal("15")

        inv_log = db_session.query(InventoryLog).filter_by(product_id=test_product.id).one()
        assert inv_log.qty_change == Decimal("5")

        audit_log = db_session.query(AuditLog).filter_by(action="STOCK_ADJUSTMENT").one()
        assert audit_log.event_type == "INVENTORY"
        assert audit_log.user_id == test_user.id
