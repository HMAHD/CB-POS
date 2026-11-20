"""Unit and integration tests for FeatureFlags service (#942)."""

import pytest

from cbpos.core.constants.audit import FEATURE_FLAG_EVENT
from cbpos.core.constants.features import Features
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, FeatureFlag, Role, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.feature_flags import FeatureFlags, feature_visible
from cbpos.core.utils.terminal_guard import CatalogReadOnlyError


@pytest.fixture(autouse=True)
def reset_feature_flags_cache(db_session):
    FeatureFlags.invalidate_cache()
    ConfigService.set("terminal_mode", "standalone")
    yield
    FeatureFlags.invalidate_cache()
    ConfigService.set("terminal_mode", "standalone")


def _get_or_create_admin(session) -> User:
    admin_role = session.query(Role).filter(Role.name == "Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin", access_level=9)
        session.add(admin_role)
        session.flush()
    admin_user = User(username="admin_test", pin_hash="hash", role_id=admin_role.id)
    session.add(admin_user)
    session.commit()
    return admin_user


def test_fresh_database_has_all_flags_off(db_session):
    """A fresh DB with no preset applied returns False for every feature flag."""
    for flag in Features.ALL:
        assert FeatureFlags.is_on(flag) is False
        assert feature_visible(flag) is False


def test_set_flag_updates_db_and_cache_and_audit(db_session):
    """Setting a flag updates the database, updates the cache, and writes an AuditLog."""
    admin_user = _get_or_create_admin(db_session)

    FeatureFlags.set(Features.WARRANTY, True, acting_user_id=admin_user.id)

    # Cache reflects it
    assert FeatureFlags.is_on(Features.WARRANTY) is True
    assert feature_visible(Features.WARRANTY) is True

    # Database row exists
    with Database().get_session() as session:
        flag = session.get(FeatureFlag, Features.WARRANTY)
        assert flag is not None
        assert flag.enabled is True
        assert flag.updated_by == admin_user.id

        # AuditLog row exists
        log = (
            session.query(AuditLog)
            .filter(AuditLog.event_type == FEATURE_FLAG_EVENT, AuditLog.action == "SET_FEATURE_FLAG")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert log is not None
        assert Features.WARRANTY in log.details


def test_set_flag_requires_permission(db_session):
    """A non-admin user without settings.features permission cannot set feature flags."""
    cashier_role = Role(name="CashierTest", access_level=1)
    db_session.add(cashier_role)
    db_session.flush()

    cashier_user = User(username="cashier_test", pin_hash="hash", role_id=cashier_role.id)
    db_session.add(cashier_user)
    db_session.commit()

    with pytest.raises(PermissionError, match="Permission denied"):
        FeatureFlags.set(Features.CREDIT_BOOK, True, acting_user_id=cashier_user.id)


def test_set_flag_requires_authentication(db_session):
    """Calling set() without acting_user_id and no logged-in user raises PermissionError."""
    from unittest.mock import patch

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=None):
        with pytest.raises(PermissionError, match="Authentication required"):
            FeatureFlags.set(Features.CREDIT_BOOK, True, acting_user_id=None)


def test_set_flag_read_only_on_till(db_session):
    """Calling set() on a till terminal raises CatalogReadOnlyError."""
    admin_user = _get_or_create_admin(db_session)

    ConfigService.set("terminal_mode", "terminal")
    with pytest.raises(CatalogReadOnlyError):
        FeatureFlags.set(Features.WARRANTY, True, acting_user_id=admin_user.id)


def test_invalidate_cache_refreshes_from_db(db_session):
    """Direct DB changes (e.g. pulled via LAN sync) take effect once invalidate_cache() is called."""
    with Database().get_session() as session:
        session.merge(FeatureFlag(name=Features.CHEQUES, enabled=True))
        session.commit()

    # Before cache invalidation, cache might still be empty/stale
    FeatureFlags.invalidate_cache()
    assert FeatureFlags.is_on(Features.CHEQUES) is True
