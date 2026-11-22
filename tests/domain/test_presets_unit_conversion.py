import pytest

from cbpos.core.constants.features import Features, ShopTypes
from cbpos.core.models import Role, User
from cbpos.core.services.feature_flags import FeatureFlags, feature_visible


@pytest.fixture(autouse=True)
def reset_cache(db_session):
    FeatureFlags.invalidate_cache()
    yield
    FeatureFlags.invalidate_cache()


@pytest.fixture
def admin_user(db_session):
    admin_role = db_session.query(Role).filter(Role.name == "Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin", access_level=9)
        db_session.add(admin_role)
        db_session.flush()
    user = User(username="admin_preset_test", pin_hash="hash", role_id=admin_role.id)
    db_session.add(user)
    db_session.commit()
    return user


def test_presets_enable_unit_conversion_for_grocery_pharmacy_hardware(db_session, admin_user):
    """Grocery, Pharmacy, Hardware presets enable UNIT_CONVERSION; others keep it off."""
    for shop_type in (ShopTypes.GROCERY, ShopTypes.PHARMACY, ShopTypes.HARDWARE):
        FeatureFlags.invalidate_cache()
        FeatureFlags.apply_preset(shop_type, acting_user_id=admin_user.id, session=db_session)
        assert FeatureFlags.is_on(Features.UNIT_CONVERSION) is True
        assert feature_visible(Features.UNIT_CONVERSION) is True


def test_presets_disable_unit_conversion_for_other_shop_types(db_session, admin_user):
    """Clothing, Phone/Electronics, Bookshop, Bakery, Other keep UNIT_CONVERSION off."""
    for shop_type in (
        ShopTypes.CLOTHING,
        ShopTypes.PHONE_ELECTRONICS,
        ShopTypes.BOOKSHOP,
        ShopTypes.BAKERY,
        ShopTypes.OTHER,
    ):
        FeatureFlags.invalidate_cache()
        FeatureFlags.apply_preset(shop_type, acting_user_id=admin_user.id, session=db_session)
        assert FeatureFlags.is_on(Features.UNIT_CONVERSION) is False
        assert feature_visible(Features.UNIT_CONVERSION) is False


def test_fresh_database_has_unit_conversion_off(db_session):
    """A fresh database before any preset application has UNIT_CONVERSION off."""
    assert FeatureFlags.is_on(Features.UNIT_CONVERSION) is False
    assert feature_visible(Features.UNIT_CONVERSION) is False
