"""Tests for shop-type presets and seeding (Decision D34, D35, Issue #942)."""

import pytest
from sqlalchemy import func

from cbpos.core.constants.features import PRESET_MATRIX, ShopTypes
from cbpos.core.models import Category, FeatureFlag, Role, Unit, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.feature_flags import FeatureFlags


@pytest.fixture(autouse=True)
def cleanup_presets():
    FeatureFlags.invalidate_cache()
    ConfigService.set("terminal_mode", "standalone")
    yield
    FeatureFlags.invalidate_cache()
    ConfigService.set("terminal_mode", "standalone")


def _get_or_create_admin(session, username="admin_preset") -> User:
    admin_role = session.query(Role).filter(Role.name == "Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin", access_level=9)
        session.add(admin_role)
        session.flush()
    admin_user = User(username=username, pin_hash="hash", role_id=admin_role.id)
    session.add(admin_user)
    session.commit()
    return admin_user


def test_apply_preset_sets_exact_matrix_flags(db_session):
    """Applying a preset sets exactly the 12 flags from the approved matrix."""
    admin_user = _get_or_create_admin(db_session, "admin_preset")

    for shop_type in ShopTypes.ALL:
        FeatureFlags.apply_preset(shop_type, acting_user_id=admin_user.id)
        matrix = PRESET_MATRIX[shop_type]
        for feature_name, expected in matrix.items():
            assert FeatureFlags.is_on(feature_name) is expected, f"Flag {feature_name} mismatch for {shop_type}"


def test_apply_preset_is_idempotent(db_session):
    """Running apply_preset multiple times does not duplicate categories or units."""
    admin_user = _get_or_create_admin(db_session, "admin_idem")

    # Apply Grocery preset twice
    FeatureFlags.apply_preset(ShopTypes.GROCERY, acting_user_id=admin_user.id, language="en")
    initial_cat_count = db_session.query(Category).count()
    initial_unit_count = db_session.query(Unit).count()

    FeatureFlags.apply_preset(ShopTypes.GROCERY, acting_user_id=admin_user.id, language="en")
    assert db_session.query(Category).count() == initial_cat_count
    assert db_session.query(Unit).count() == initial_unit_count


def test_preset_unit_deduplication_by_name_and_abbrev(db_session):
    """Seeding units checks both name and abbreviation so duplicate names or abbreviations are avoided."""
    admin_user = _get_or_create_admin(db_session, "admin_unit")

    # Pre-insert a unit with name 'Tablet' but different abbr 'tbl'
    db_session.add(Unit(name="Tablet", abbreviation="tbl", decimal_places=0))
    db_session.commit()

    # Pharmacy preset seeds ('Tablet', 'tab', 0)
    FeatureFlags.apply_preset(ShopTypes.PHARMACY, acting_user_id=admin_user.id)

    # Should not throw IntegrityError, and should not duplicate the 'Tablet' name
    tablets = db_session.query(Unit).filter(func.lower(Unit.name) == "tablet").all()
    assert len(tablets) == 1


def test_preset_category_seeding_languages(db_session):
    """Categories are seeded in the chosen language (en, si, ta) per Decision D35 Option A."""
    admin_user = _get_or_create_admin(db_session, "admin_lang")

    # Sinhala
    FeatureFlags.apply_preset(ShopTypes.BAKERY, acting_user_id=admin_user.id, language="si")
    paan = db_session.query(Category).filter(Category.name == "පාන් සහ බනිස්").first()
    assert paan is not None
    assert paan.parent_id is None

    # Tamil
    FeatureFlags.apply_preset(ShopTypes.CLOTHING, acting_user_id=admin_user.id, language="ta")
    aangal = db_session.query(Category).filter(Category.name == "ஆண்கள் ஆடை").first()
    assert aangal is not None
    assert aangal.parent_id is None


def test_preset_other_seeds_no_categories_and_ensures_pcs(db_session):
    """'Other' shop type seeds zero categories and ensures pcs unit exists."""
    admin_user = _get_or_create_admin(db_session, "admin_other")

    initial_cats = db_session.query(Category).count()
    FeatureFlags.apply_preset(ShopTypes.OTHER, acting_user_id=admin_user.id)

    # No new categories added
    assert db_session.query(Category).count() == initial_cats

    # 'pcs' unit exists
    pcs = db_session.query(Unit).filter(func.lower(Unit.abbreviation) == "pcs").first()
    assert pcs is not None


def test_apply_preset_transaction_session_propagation(db_session):
    """apply_preset works cleanly when passed an existing uncommitted session."""
    admin_role = db_session.query(Role).filter(Role.name == "Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin", access_level=9)
        db_session.add(admin_role)
        db_session.flush()
    admin_user = User(username="admin_tx", pin_hash="hash", role_id=admin_role.id)
    db_session.add(admin_user)
    db_session.flush()

    FeatureFlags.apply_preset(
        ShopTypes.HARDWARE,
        acting_user_id=admin_user.id,
        session=db_session,
    )

    # Within session, flags are present
    assert db_session.query(FeatureFlag).count() == 12
