"""UI feature gating tests for Issue #942."""

import pytest

from cbpos.core.constants.features import Features
from cbpos.core.constants.status import PaymentMethodKind
from cbpos.core.models import PaymentMethod, Role, User
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.core.services.payment_service import PaymentService
from cbpos.core.services.permission_service import PermissionService


@pytest.fixture(autouse=True)
def cleanup_flags():
    FeatureFlags.invalidate_cache()
    yield
    FeatureFlags.invalidate_cache()


def _make_admin(session):
    role = session.query(Role).filter(Role.name == "Admin").first()
    if not role:
        role = Role(name="Admin", access_level=9)
        session.add(role)
        session.flush()
    user = User(username="admin_ui_gate", pin_hash="hash", role_id=role.id)
    session.add(user)
    session.commit()
    return user


def test_management_tabs_hidden_when_features_off(db_session):
    """Warranty and Credit Book tabs are hidden in management_tabs() when feature flags are off."""
    admin = _make_admin(db_session)

    # Ensure flags are off
    FeatureFlags.set(Features.WARRANTY, False, acting_user_id=admin.id)
    FeatureFlags.set(Features.CREDIT_BOOK, False, acting_user_id=admin.id)

    tabs = PermissionService.management_tabs(admin)
    assert "warranty" not in tabs
    assert "credit_book" not in tabs

    # Turn on
    FeatureFlags.set(Features.WARRANTY, True, acting_user_id=admin.id)
    FeatureFlags.set(Features.CREDIT_BOOK, True, acting_user_id=admin.id)

    tabs = PermissionService.management_tabs(admin)
    assert "warranty" in tabs
    assert "credit_book" in tabs


def test_payment_methods_filtered_when_credit_and_cheques_off(db_session):
    """Credit and Cheque payment methods are omitted from active methods when flags are off."""
    admin = _make_admin(db_session)

    # Seed payment methods if not present
    for kind, name in [
        (PaymentMethodKind.CASH, "Cash"),
        (PaymentMethodKind.CREDIT, "Credit"),
        (PaymentMethodKind.CHEQUE, "Cheque"),
    ]:
        m = db_session.query(PaymentMethod).filter(PaymentMethod.kind == kind).first()
        if not m:
            db_session.add(PaymentMethod(name=name, kind=kind, is_active=True))
    db_session.commit()

    # Off
    FeatureFlags.set(Features.CREDIT_BOOK, False, acting_user_id=admin.id)
    FeatureFlags.set(Features.CHEQUES, False, acting_user_id=admin.id)

    active = PaymentService.get_active_methods()
    kinds = {m.kind for m in active}
    assert PaymentMethodKind.CREDIT not in kinds
    assert PaymentMethodKind.CHEQUE not in kinds
    assert PaymentMethodKind.CASH in kinds

    # On
    FeatureFlags.set(Features.CREDIT_BOOK, True, acting_user_id=admin.id)
    FeatureFlags.set(Features.CHEQUES, True, acting_user_id=admin.id)

    active_on = PaymentService.get_active_methods()
    kinds_on = {m.kind for m in active_on}
    assert PaymentMethodKind.CREDIT in kinds_on
    assert PaymentMethodKind.CHEQUE in kinds_on


def test_product_editor_serial_mode_gated_by_feature(app_fixture, db_session):
    """ProductEditor serial tracking is hidden when SERIAL_TRACKING feature flag is off."""
    from cbpos.ui.dialogs.product_editor import ProductEditor

    admin = _make_admin(db_session)

    # 1. Flag OFF, Warranty ON
    FeatureFlags.set(Features.WARRANTY, True, acting_user_id=admin.id)
    FeatureFlags.set(Features.SERIAL_TRACKING, False, acting_user_id=admin.id)

    editor_off = ProductEditor()
    assert hasattr(editor_off, "_serial_visible")
    assert editor_off._serial_visible is False

    # 2. Flag ON, Warranty ON
    FeatureFlags.set(Features.SERIAL_TRACKING, True, acting_user_id=admin.id)
    editor_on = ProductEditor()
    assert editor_on._serial_visible is True
