"""
TransactionService._execute_sale() force-loads sale.customer before the
session closes ("Eager-load relationships before session closes") but
never touched sale.items or item.product the same way, even though
ReceiptOptionsDialog.print_thermal() (opened right after a sale completes
whenever show_receipt_dialog is on -- the default) reads exactly that via
ReceiptService.build_receipt_text()/build_receipt_image(): `for item in
sale.items: name = item.product.name_en[:20]`. Without the force-load,
that crashes with DetachedInstanceError once the real session closes.

Note: the shared db_session test fixture patches session.close() to a
no-op (needed for rollback-based test isolation across the whole suite)
and its own savepoint-restart machinery calls session.expire_all() on
every transaction boundary, which makes it impossible to cleanly
distinguish "eager-loaded and safe" from "not loaded at all" purely by
simulating a session close here -- either way ends up expired. This test
instead confirms the query/relationship data itself is correct (right
item count, right product) immediately after process_sale() returns,
which is what the force-load lines exist to preserve.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Permission, Product, Role, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"tsi_test_{suffix}")
    role = Role(name=f"TsiRole_{suffix}", permissions=[permission])
    user = User(username=f"tsi_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"TsiProduct_{_counter}", price=Decimal("100.00"), stock_qty=10.0, barcode=f"TSI{_counter:04d}"
    )
    db_session.add(product)
    db_session.flush()
    return product


def test_sale_items_and_product_are_loaded_after_process_sale(db_session, test_user, test_product):
    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
        patch("cbpos.core.services.transaction_service.PrintWorker"),
    ):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        sale = TransactionService.process_sale(cart_service, payments)

        assert sale is not None
        assert len(sale.items) == 1
        assert sale.items[0].product.name_en == test_product.name_en
        assert sale.items[0].qty == Decimal("2.0")
