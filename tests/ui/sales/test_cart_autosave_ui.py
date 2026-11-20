"""UI tests for SalesView power-cut autosave debounce and recovery integration (#932)."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.models import Product, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.ui.dialogs.autosave_recovery_dialog import AutosaveAction
from cbpos.ui.views.sales_view import SalesView


@pytest.fixture
def test_user(db_session):
    """Create test cashier user."""
    role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
    if not role:
        role = Role(name=ADMIN_ROLE_NAME)
        db_session.add(role)
        db_session.commit()

    user = db_session.query(User).filter_by(username="ui_sales_cashier").first()
    if not user:
        user = User(username="ui_sales_cashier", pin_hash="hash", role_id=role.id, is_active=True)
        db_session.add(user)
        db_session.commit()

    AuthService._current_user = user
    yield user
    AuthService._current_user = None


@pytest.fixture
def sample_item(db_session):
    """Create sample active product."""
    prod = db_session.query(Product).filter_by(barcode="UI-AUTO-01").first()
    if not prod:
        prod = Product(
            name_en="UI Autosave Product",
            barcode="UI-AUTO-01",
            price=Decimal("200.00"),
            cost=Decimal("120.00"),
            stock_qty=Decimal("50.000"),
            is_active=True,
        )
        db_session.add(prod)
        db_session.commit()
    return prod


@pytest.mark.ui
def test_issue_932_sales_view_autosave_debounce(qtbot, db_session, test_user, sample_item):
    """Adding an item starts the 1000ms debounce timer; timeout dispatches background worker."""
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, True, acting_user_id=test_user.id)
    terminal_id = "TERM-UI-DEBOUNCE"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)

    assert view._autosave_timer.isActive() is False

    # Add item to cart
    view.cart_service.add_item(sample_item, Decimal("1.000"))
    view.update_cart_display()

    # Timer must be active with 1000ms interval
    assert view._autosave_timer.isActive() is True
    assert view._autosave_timer.interval() == 1000

    # Wait for timer to timeout
    with qtbot.waitSignal(view._autosave_timer.timeout, timeout=2000):
        pass

    # Record must be persisted in DB
    summary = CartAutosaveService.get_autosave_summary(terminal_id)
    assert summary is not None
    assert summary["item_count"] == 1
    assert summary["total"] == Decimal("200.00")


@pytest.mark.ui
def test_issue_932_sales_view_clear_cancels_and_deletes(qtbot, db_session, test_user, sample_item):
    """Clearing the cart stops the timer and purges any autosave row."""
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, True, acting_user_id=test_user.id)
    terminal_id = "TERM-UI-CLEAR"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)

    # Add item
    view.cart_service.add_item(sample_item, Decimal("2.000"))
    view.update_cart_display()
    assert view._autosave_timer.isActive() is True

    # Empty cart
    view.cart_service.clear()
    view.update_cart_display()

    # Timer must be stopped and row deleted
    assert view._autosave_timer.isActive() is False
    assert CartAutosaveService.has_autosave(terminal_id) is False


@pytest.mark.ui
def test_issue_932_sales_view_feature_flag_off_no_autosave(qtbot, db_session, test_user, sample_item):
    """When power_cut_autosave is OFF, timer is never started."""
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, False, acting_user_id=test_user.id)
    terminal_id = "TERM-UI-FLAG-OFF"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)

    view.cart_service.add_item(sample_item, Decimal("1.000"))
    view.update_cart_display()

    assert view._autosave_timer.isActive() is False
    assert CartAutosaveService.has_autosave(terminal_id) is False


@pytest.mark.ui
def test_issue_932_sales_view_recovery_restores_cart(qtbot, db_session, test_user, sample_item):
    """On recovery dialog CONTINUE, cart is restored with full fidelity."""
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, True, acting_user_id=test_user.id)
    terminal_id = "TERM-UI-RECOVER"
    ConfigService.set("terminal_id", terminal_id)

    # Pre-save an autosave
    cart = CartService()
    cart.add_item(sample_item, Decimal("3.000"))
    snap = CartAutosaveService.snapshot_cart(cart)
    CartAutosaveService.save(snap, terminal_id, 1)

    view = SalesView()
    qtbot.addWidget(view)
    assert len(view.cart_service.items) == 0

    from cbpos.ui.dialogs.autosave_recovery_dialog import AutosaveRecoveryDialog

    def _mock_exec(dlg_self):
        dlg_self.action = AutosaveAction.CONTINUE
        return True

    with patch.object(AutosaveRecoveryDialog, "exec", _mock_exec):
        view.check_autosave_recovery()

    # Cart must now be restored
    assert len(view.cart_service.items) == 1
    assert view.cart_service.items[0]["qty"] == Decimal("3.000")
    assert view.cart_service.items[0]["product"].id == sample_item.id
    # Row must be purged after restore
    assert CartAutosaveService.has_autosave(terminal_id) is False
