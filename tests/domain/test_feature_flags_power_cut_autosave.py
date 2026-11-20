"""Tests for power_cut_autosave feature flag behavior (Phase 10B.1 / #932)."""

from decimal import Decimal

import pytest

from cbpos.core.constants.features import PRESET_MATRIX, Features, ShopTypes
from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.models import Product, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.feature_flags import FeatureFlags


@pytest.fixture
def admin_user(db_session):
    """Create and authenticate an admin user."""
    admin_role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
    if not admin_role:
        admin_role = Role(name=ADMIN_ROLE_NAME)
        db_session.add(admin_role)
        db_session.commit()

    admin = db_session.query(User).filter_by(username="admin_test_flags").first()
    if not admin:
        admin = User(username="admin_test_flags", pin_hash="hash", role_id=admin_role.id, is_active=True)
        db_session.add(admin)
        db_session.commit()

    AuthService._current_user = admin
    yield admin
    AuthService._current_user = None


@pytest.mark.domain
def test_issue_932_preset_matrix_enables_power_cut_autosave():
    """All 8 shop presets (including Other) enable power_cut_autosave per Decision D36."""
    for shop_type in ShopTypes.ALL:
        assert PRESET_MATRIX[shop_type].get(Features.POWER_CUT_AUTOSAVE) is True, (
            f"Shop type {shop_type} must enable power_cut_autosave by default"
        )


@pytest.mark.domain
def test_issue_932_fresh_db_power_cut_autosave_off(db_session):
    """A fresh database with no applied preset has power_cut_autosave OFF."""
    FeatureFlags.invalidate_cache()
    assert FeatureFlags.is_on(Features.POWER_CUT_AUTOSAVE) is False


@pytest.mark.domain
def test_issue_932_preset_application_enables_flag(db_session, admin_user):
    """Applying a shop preset enables power_cut_autosave in the database."""
    FeatureFlags.apply_preset(ShopTypes.GROCERY, acting_user_id=admin_user.id)
    assert FeatureFlags.is_on(Features.POWER_CUT_AUTOSAVE) is True


@pytest.mark.domain
def test_issue_932_disabling_flag_deletes_all_autosaves(db_session, admin_user):
    """Turning off power_cut_autosave purges all existing autosaves."""
    # Enable feature
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, True, acting_user_id=admin_user.id)
    assert FeatureFlags.is_on(Features.POWER_CUT_AUTOSAVE) is True

    # Seed product and autosave on multiple terminals
    prod = Product(
        name_en="Flag Test Item",
        barcode="FLAG-01",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        is_active=True,
    )
    db_session.add(prod)
    db_session.commit()

    cart = CartService()
    cart.add_item(prod, Decimal("1.000"))
    snap = CartAutosaveService.snapshot_cart(cart)

    CartAutosaveService.save(snap, "TERM-01", 1)
    CartAutosaveService.save(snap, "TERM-02", 1)

    assert CartAutosaveService.has_autosave("TERM-01") is True
    assert CartAutosaveService.has_autosave("TERM-02") is True

    # Disable feature flag
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, False, acting_user_id=admin_user.id)
    assert FeatureFlags.is_on(Features.POWER_CUT_AUTOSAVE) is False

    # Autosaves should be deleted
    assert CartAutosaveService.has_autosave("TERM-01") is False
    assert CartAutosaveService.has_autosave("TERM-02") is False
