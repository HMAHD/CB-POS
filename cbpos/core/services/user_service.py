import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.role_service import ADMIN_ROLE_NAME


class UserService:
    """
    Service to handle user management operations.
    Enforces strict security boundaries for self-service updates.
    """

    @staticmethod
    def update_user_profile(user_id: int, display_name: str, new_pin: str = None) -> bool:
        """
        Update the logged-in user's profile.
        Security: Only allows updating own display name and PIN.
        """
        try:
            with Database().get_session() as session:
                user = session.get(User, user_id)
                if not user:
                    return False

                # 1. Update Display Name (Safe)
                user.username = display_name.strip()

                # 2. Update PIN (If provided)
                if new_pin:
                    if len(new_pin) < 4 or not new_pin.isdigit():
                        raise ValueError("PIN must be at least 4 digits")
                    if AuthService.is_pin_in_use(new_pin, exclude_user_id=user_id):
                        raise ValueError("pin_in_use")
                    # Hash the new PIN
                    user.pin_hash = AuthService.hash_pin(new_pin)

                # 3. Audit Log
                # Log the change for security auditing
                current_user = AuthService.get_current_user()
                logger_id = current_user.id if current_user else user_id

                log = AuditLog(
                    user_id=logger_id,
                    action="PROFILE_UPDATE",
                    event_type="SECURITY",
                    details=f"User {user_id} updated profile. PIN Changed: {bool(new_pin)}",
                )
                session.add(log)
                return True

        except ValueError:
            raise
        except Exception as e:
            logging.error("Profile Update Failed: %s", e)
            return False

    @staticmethod
    def update_admin_pin(new_pin: str) -> bool:
        """Update the admin user's PIN during first-run setup."""
        try:
            with Database().get_session() as session:
                admin = session.query(User).filter(User.username == "admin").first()
                if not admin:
                    return False
                admin.pin_hash = AuthService.hash_pin(new_pin)
                return True
        except Exception as e:
            logging.error("Update Admin PIN Failed: %s", e)
            return False

    @staticmethod
    def get_recent_activity(
        user_id: int | None = None,
        limit: int = 200,
        event_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list:
        """
        Retrieve recent audit logs, optionally narrowed by user, event type,
        or a timestamp range.
        """
        try:
            with Database().get_session() as session:
                query = session.query(AuditLog)

                if user_id is not None:
                    query = query.filter(AuditLog.user_id == user_id)

                if event_type is not None:
                    query = query.filter(AuditLog.event_type == event_type)

                if date_from is not None:
                    query = query.filter(AuditLog.timestamp >= date_from)

                if date_to is not None:
                    query = query.filter(AuditLog.timestamp <= date_to)

                logs = query.options(joinedload(AuditLog.user)).order_by(AuditLog.timestamp.desc()).limit(limit).all()
                # Detach objects for UI use
                for log in logs:
                    session.expunge(log)
                return logs

        except Exception as e:
            logging.error("Failed to fetch activity: %s", e)
            return []

    @staticmethod
    def get_all_users() -> list:
        """Retrieve all users."""
        try:
            with Database().get_session() as session:
                users = session.query(User).options(joinedload(User.role)).all()
                for user in users:
                    session.expunge(user)
                return users
        except Exception as e:
            logging.error("Failed to fetch users: %s", e)
            return []

    @staticmethod
    def get_all_roles() -> list:
        """Retrieve all roles."""
        try:
            with Database().get_session() as session:
                from sqlalchemy.orm import joinedload

                from cbpos.core.models import Role

                roles = session.query(Role).options(joinedload(Role.permissions)).all()
                return roles
        except Exception as e:
            logging.error("Failed to fetch roles: %s", e)
            return []

    @staticmethod
    def create_user(username: str, pin: str, role_id: int) -> bool:
        """Create a new user."""
        try:
            with Database().get_session() as session:
                # Check if username exists
                if session.query(User).filter(User.username == username).first():
                    raise ValueError("Username already exists")

                if AuthService.is_pin_in_use(pin):
                    raise ValueError("pin_in_use")

                pin_hash = AuthService.hash_pin(pin)

                user = User(username=username, pin_hash=pin_hash, role_id=role_id, is_active=True)
                session.add(user)
                session.flush()

                # Log
                current_user = AuthService.get_current_user()
                logger_id = current_user.id if current_user else user.id  # Fallback

                log = AuditLog(
                    user_id=logger_id,
                    action="CREATE_USER",
                    event_type="SECURITY",
                    details=f"Created user {username}",
                )
                session.add(log)
                return True
        except ValueError:
            raise
        except Exception as e:
            logging.error("Create User Failed: %s", e)
            raise e

    @staticmethod
    def is_last_active_admin(user_id: int) -> bool:
        """Check if user_id is the only active Admin in the system."""
        try:
            with Database().get_session() as session:
                admin_role = session.execute(select(Role).where(Role.name == ADMIN_ROLE_NAME)).scalar_one_or_none()
                if not admin_role:
                    return False

                user = session.get(User, user_id)
                if not user or not user.is_active or user.role_id != admin_role.id:
                    return False

                other_admins_count = (
                    session.execute(
                        select(func.count(User.id)).where(
                            User.is_active == True,  # noqa: E712
                            User.role_id == admin_role.id,
                            User.id != user_id,
                        )
                    ).scalar()
                    or 0
                )
                return other_admins_count == 0
        except Exception:
            return False

    @staticmethod
    def update_user(user_id: int, username: str, pin: str | None, role_id: int, is_active: bool) -> bool:
        """Update an existing user."""
        try:
            with Database().get_session() as session:
                user = session.get(User, user_id)
                if not user:
                    return False

                # Guard against demoting or deactivating the last active Admin
                admin_role = session.execute(select(Role).where(Role.name == ADMIN_ROLE_NAME)).scalar_one_or_none()
                if admin_role and user.is_active and user.role_id == admin_role.id:
                    leaving_admin = (not is_active) or (role_id != admin_role.id)
                    if leaving_admin:
                        other_admins_count = (
                            session.execute(
                                select(func.count(User.id)).where(
                                    User.is_active == True,  # noqa: E712
                                    User.role_id == admin_role.id,
                                    User.id != user_id,
                                )
                            ).scalar()
                            or 0
                        )
                        if other_admins_count == 0:
                            raise ValueError("last_admin")

                # Reactivation check: if user was inactive and is being activated, new PIN is required
                if not user.is_active and is_active and not pin:
                    raise ValueError("pin_required_on_reactivate")

                user.username = username
                user.role_id = role_id
                user.is_active = is_active

                if pin:
                    if AuthService.is_pin_in_use(pin, exclude_user_id=user_id):
                        raise ValueError("pin_in_use")
                    user.pin_hash = AuthService.hash_pin(pin)

                # Log
                current_user = AuthService.get_current_user()
                logger_id = current_user.id if current_user else user_id

                log = AuditLog(
                    user_id=logger_id,
                    action="UPDATE_USER",
                    event_type="SECURITY",
                    details=f"Updated user {username} (ID: {user_id})",
                )
                session.add(log)
                return True
        except ValueError:
            raise
        except Exception as e:
            logging.error("Update User Failed: %s", e)
            raise e
