"""Tests for Issue #893: Lowering cart quantity requires sales.void permission and AuditLog."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import AuditLog, Product, User
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


def _make_product(name="Test Item", price="50.00", stock=100):
    return Product(
        name_en=name,
        barcode="BAR-893",
        price=Decimal(price),
        cost=Decimal("20.00"),
        stock_qty=Decimal(str(stock)),
        price_change_allowed=True,
    )


def test_issue_893_reduce_qty_without_void_permission_cancelled(db_session, monkeypatch):
    """When lowering quantity and override is cancelled, quantity remains unchanged and no audit row is written."""
    cashier = User(id=101, username="cashier_893", pin_hash="h", role_id=1, is_active=True)
    monkeypatch.setattr("cbpos.core.services.auth_service.AuthService.get_current_user", lambda: cashier)

    override_calls = []

    def mock_override(perm, parent=None):
        override_calls.append(perm)
        return None

    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", mock_override)

    view = SalesView()
    product = _make_product()
    db_session.add(product)
    db_session.flush()

    view.cart_service.add_item(product, qty=Decimal("5"))
    view.update_cart_display()
    view.cart_table.setCurrentCell(0, 0)

    # Mock QuantityDialog returning 2 (< 5)
    fake_dialog = MagicMock()
    fake_dialog.exec.return_value = 1
    fake_dialog.get_quantity.return_value = Decimal("2")
    monkeypatch.setattr("cbpos.ui.views.sales_view.QuantityDialog", MagicMock(return_value=fake_dialog))

    view.change_line_quantity()

    # Permission was checked
    assert Permissions.SALES_VOID in override_calls
    # Quantity was NOT reduced
    assert view.cart_service.items[0]["qty"] == Decimal("5")
    # No audit log was written
    audit_count = len(db_session.execute(select(AuditLog).where(AuditLog.action == "LINE_QTY_REDUCED")).all())
    assert audit_count == 0

    view.deleteLater()


def test_issue_893_reduce_qty_with_void_permission_succeeds_and_audited(db_session, monkeypatch):
    """When lowering quantity with permission/override, quantity updates and one LINE_QTY_REDUCED audit row is written."""
    cashier = User(username="cashier_893", pin_hash="h", role_id=None, is_active=True)
    manager = User(username="manager_893", pin_hash="h", role_id=None, is_active=True)
    product = _make_product()
    db_session.add_all([cashier, manager, product])
    db_session.commit()

    monkeypatch.setattr("cbpos.core.services.auth_service.AuthService.get_current_user", lambda: cashier)

    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent=None: manager,
    )

    view = SalesView()

    view.cart_service.add_item(product, qty=Decimal("5"))
    view.update_cart_display()
    view.cart_table.setCurrentCell(0, 0)

    fake_dialog = MagicMock()
    fake_dialog.exec.return_value = 1
    fake_dialog.get_quantity.return_value = Decimal("2")
    monkeypatch.setattr("cbpos.ui.views.sales_view.QuantityDialog", MagicMock(return_value=fake_dialog))

    view.change_line_quantity()

    # Quantity reduced
    assert view.cart_service.items[0]["qty"] == Decimal("2")

    # Exactly one audit row written
    logs = db_session.execute(select(AuditLog).where(AuditLog.action == "LINE_QTY_REDUCED")).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.action == "LINE_QTY_REDUCED"
    assert "2" in log.details and "5" in log.details

    view.deleteLater()


def test_issue_893_increasing_qty_needs_no_permission(db_session, monkeypatch):
    """Increasing quantity does not prompt for permission and does not write an audit row."""
    cashier = User(id=101, username="cashier_893", pin_hash="h", role_id=1, is_active=True)
    monkeypatch.setattr("cbpos.core.services.auth_service.AuthService.get_current_user", lambda: cashier)

    override_calls = []
    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent=None: override_calls.append(perm),
    )

    view = SalesView()
    product = _make_product()
    db_session.add(product)
    db_session.flush()

    view.cart_service.add_item(product, qty=Decimal("2"))
    view.update_cart_display()
    view.cart_table.setCurrentCell(0, 0)

    fake_dialog = MagicMock()
    fake_dialog.exec.return_value = 1
    fake_dialog.get_quantity.return_value = Decimal("5")
    monkeypatch.setattr("cbpos.ui.views.sales_view.QuantityDialog", MagicMock(return_value=fake_dialog))

    view.change_line_quantity()

    # No override prompt called
    assert len(override_calls) == 0
    # Quantity was updated
    assert view.cart_service.items[0]["qty"] == Decimal("5")
    # No audit log
    logs = db_session.execute(select(AuditLog).where(AuditLog.action == "LINE_QTY_REDUCED")).scalars().all()
    assert len(logs) == 0

    view.deleteLater()
