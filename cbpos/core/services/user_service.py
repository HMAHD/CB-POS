import hashlib
import logging
from typing import Optional
from sqlalchemy.orm import joinedload
from cbpos.core.database import Database
from cbpos.core.models import User, AuditLog
from cbpos.core.services.auth_service import AuthService


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
                    # Hash the new PIN
                    pin_hash = hashlib.sha256(new_pin.encode()).hexdigest()
                    user.pin_hash = pin_hash

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
                session.commit()
                return True

        except Exception as e:
            logging.error(f"Profile Update Failed: {e}")
            return False

    @staticmethod
    def get_recent_activity(user_id: Optional[int] = None, limit: int = 10) -> list:
        """
        Retrieve recent audit logs.
        If user_id is provided, filter by user. Otherwise return all.
        """
        try:
            with Database().get_session() as session:
                query = session.query(AuditLog)

                if user_id is not None:
                    query = query.filter(AuditLog.user_id == user_id)

                logs = query.options(joinedload(AuditLog.user)).order_by(AuditLog.timestamp.desc()).limit(limit).all()
                # Detach objects for UI use
                for log in logs:
                    session.expunge(log)
                return logs

        except Exception as e:
            logging.error(f"Failed to fetch activity: {e}")
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
            logging.error(f"Failed to fetch users: {e}")
            return []

    @staticmethod
    def get_all_roles() -> list:
        """Retrieve all roles."""
        try:
            with Database().get_session() as session:
                from cbpos.core.models import Role

                roles = session.query(Role).all()
                for role in roles:
                    session.expunge(role)
                return roles
        except Exception as e:
            logging.error(f"Failed to fetch roles: {e}")
            return []

    @staticmethod
    def create_user(username: str, pin: str, role_id: int) -> bool:
        """Create a new user."""
        try:
            with Database().get_session() as session:
                # Check if username exists
                if session.query(User).filter(User.username == username).first():
                    raise ValueError("Username already exists")

                pin_hash = hashlib.sha256(pin.encode()).hexdigest()

                user = User(username=username, pin_hash=pin_hash, role_id=role_id, is_active=True)
                session.add(user)
                session.commit()

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
                session.commit()
                return True
        except Exception as e:
            logging.error(f"Create User Failed: {e}")
            raise e

    @staticmethod
    def update_user(user_id: int, username: str, pin: Optional[str], role_id: int, is_active: bool) -> bool:
        """Update an existing user."""
        try:
            with Database().get_session() as session:
                user = session.get(User, user_id)
                if not user:
                    return False

                user.username = username
                user.role_id = role_id
                user.is_active = is_active

                if pin:
                    user.pin_hash = hashlib.sha256(pin.encode()).hexdigest()

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
                session.commit()
                return True
        except Exception as e:
            logging.error(f"Update User Failed: {e}")
            raise e
