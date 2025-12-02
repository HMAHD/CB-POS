import hashlib
import logging
from typing import Optional
from cbpos.core.database import Database
from cbpos.core.models import User, AuditLog
from cbpos.core.services.auth_service import AuthService


class UserService:
    """
    Service to handle user management operations.
    Enforces strict security boundaries for self-service updates.
    """

    @staticmethod
    def update_user_profile(user_id: int, display_name: str, new_pin: Optional[str] = None) -> bool:
        """
        Update the profile of a specific user.
        STRICTLY LIMITED to display_name and pin.
        Cannot update role, active status, or other sensitive fields.

        Args:
            user_id: ID of the user to update.
            display_name: New display name.
            new_pin: Optional new PIN (plain text).

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            with Database().get_session() as session:
                user = session.get(User, user_id)
                if not user:
                    return False

                # 1. Update Display Name (Safe)
                user.username = display_name.strip()  # Sanitize input

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
    def get_recent_activity(user_id: int, limit: int = 10) -> list:
        """
        Retrieve recent audit logs for a specific user.
        """
        try:
            with Database().get_session() as session:
                logs = (
                    session.query(AuditLog)
                    .filter(AuditLog.user_id == user_id)
                    .order_by(AuditLog.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                # Detach objects for UI use
                for log in logs:
                    session.expunge(log)
                return logs
        except Exception as e:
            logging.error(f"Failed to fetch activity: {e}")
            return []
