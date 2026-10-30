"""Domain tests for UserService — Issue #857: Duplicate PIN prevention and reactivation PIN requirements."""

import pytest

from cbpos.core.models import Permission, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.user_service import UserService


@pytest.fixture
def user_roles(db_session):
    """Seed roles for user tests."""
    perm = Permission(code="sales.create")
    role = Role(name="Cashier_Role_857", permissions=[perm])
    db_session.add_all([perm, role])
    db_session.commit()
    return role


def test_issue_857_create_user_with_existing_pin_raises(db_session, user_roles):
    """Creating a user with a PIN held by an active user raises ValueError('pin_in_use')."""
    user1 = User(
        username="user1_857",
        pin_hash=AuthService.hash_pin("1234"),
        role_id=user_roles.id,
        is_active=True,
    )
    db_session.add(user1)
    db_session.commit()

    with pytest.raises(ValueError, match="pin_in_use"):
        UserService.create_user("user2_857", "1234", user_roles.id)


def test_issue_857_update_user_to_existing_pin_raises(db_session, user_roles):
    """Updating a user to a PIN held by another active user raises ValueError('pin_in_use')."""
    user1 = User(
        username="user1_857",
        pin_hash=AuthService.hash_pin("1234"),
        role_id=user_roles.id,
        is_active=True,
    )
    user2 = User(
        username="user2_857",
        pin_hash=AuthService.hash_pin("5678"),
        role_id=user_roles.id,
        is_active=True,
    )
    db_session.add_all([user1, user2])
    db_session.commit()

    with pytest.raises(ValueError, match="pin_in_use"):
        UserService.update_user(user2.id, "user2_857", "1234", user_roles.id, True)


def test_issue_857_profile_pin_change_to_existing_pin_raises(db_session, user_roles):
    """Self-changing PIN in profile to another active user's PIN raises ValueError('pin_in_use')."""
    user1 = User(
        username="user1_857",
        pin_hash=AuthService.hash_pin("1234"),
        role_id=user_roles.id,
        is_active=True,
    )
    user2 = User(
        username="user2_857",
        pin_hash=AuthService.hash_pin("5678"),
        role_id=user_roles.id,
        is_active=True,
    )
    db_session.add_all([user1, user2])
    db_session.commit()

    with pytest.raises(ValueError, match="pin_in_use"):
        UserService.update_user_profile(user2.id, "user2_display", "1234")


def test_issue_857_same_user_keeping_own_pin_is_allowed(db_session, user_roles):
    """Updating own record while providing own existing PIN succeeds without conflict."""
    user1 = User(
        username="user1_857",
        pin_hash=AuthService.hash_pin("1234"),
        role_id=user_roles.id,
        is_active=True,
    )
    db_session.add(user1)
    db_session.commit()

    assert UserService.update_user(user1.id, "user1_renamed", "1234", user_roles.id, True) is True
    assert UserService.update_user_profile(user1.id, "user1_profile", "1234") is True


def test_issue_857_reactivation_requires_new_pin(db_session, user_roles):
    """Reactivating an inactive user requires a new PIN and validates against duplicates."""
    active_user = User(
        username="active_857",
        pin_hash=AuthService.hash_pin("1234"),
        role_id=user_roles.id,
        is_active=True,
    )
    inactive_user = User(
        username="inactive_857",
        pin_hash=AuthService.hash_pin("9999"),
        role_id=user_roles.id,
        is_active=False,
    )
    db_session.add_all([active_user, inactive_user])
    db_session.commit()

    # 1. Reactivating without providing a PIN raises ValueError('pin_required_on_reactivate')
    with pytest.raises(ValueError, match="pin_required_on_reactivate"):
        UserService.update_user(inactive_user.id, "inactive_857", None, user_roles.id, True)

    # 2. Reactivating with a PIN already in use by active user raises ValueError('pin_in_use')
    with pytest.raises(ValueError, match="pin_in_use"):
        UserService.update_user(inactive_user.id, "inactive_857", "1234", user_roles.id, True)

    # 3. Reactivating with an unused PIN succeeds
    assert UserService.update_user(inactive_user.id, "inactive_857", "8888", user_roles.id, True) is True
    db_session.refresh(inactive_user)
    assert inactive_user.is_active is True
    assert AuthService._verify_against_hash("8888", inactive_user.pin_hash) is True
