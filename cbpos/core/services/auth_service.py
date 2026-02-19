import hashlib
import logging
from typing import Optional
from sqlalchemy.orm import joinedload
from cbpos.core.database import Database
from cbpos.core.models import User

logger = logging.getLogger(__name__)


class AuthService:
    """
    Service to handle user authentication and session management.
    """

    _current_user: Optional[User] = None

    @staticmethod
    def verify_pin(pin: str) -> Optional[User]:
        """
        Verify the provided PIN against the database.

        Args:
            pin (str): The PIN entered by the user.

        Returns:
            Optional[User]: The User object if authentication is successful, else None.
        """
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()

        db = Database()
        with db.get_session() as session:
            # Eagerly load the role to prevent DetachedInstanceError later
            user = (
                session.query(User)
                .options(joinedload(User.role))
                .filter(User.pin_hash == pin_hash, User.is_active.is_(True))
                .first()
            )
            if user:
                # Detach user and role to keep available after session close
                if user.role:
                    _ = user.role.name  # Force load
                    session.expunge(user.role)
                session.expunge(user)

                AuthService._current_user = user

                # Log Login
                try:
                    from cbpos.core.models import AuditLog
                    from cbpos.core.services.config_service import ConfigService

                    terminal_id = ConfigService.get("terminal_id") or "TERM-01"
                    log = AuditLog(
                        user_id=user.id,
                        action="User Login",
                        event_type="LOGIN",
                        terminal_id=terminal_id,
                        details="Successful login via PIN",
                    )
                    session.add(log)
                    session.commit()
                except Exception as e:
                    logger.error(f"Failed to write login audit log: {e}")

                return user
        return None

    @staticmethod
    def get_current_user() -> Optional[User]:
        """Return the currently logged-in user."""
        return AuthService._current_user

    @staticmethod
    def logout():
        """Clear the current user session."""
        if AuthService._current_user:
            try:
                db = Database()
                with db.get_session() as session:
                    from cbpos.core.models import AuditLog
                    from cbpos.core.services.config_service import ConfigService

                    terminal_id = ConfigService.get("terminal_id") or "TERM-01"
                    log = AuditLog(
                        user_id=AuthService._current_user.id,
                        action="User Logout",
                        event_type="LOGOUT",
                        terminal_id=terminal_id,
                        details="Manual logout",
                    )
                    session.add(log)
                    session.commit()
            except Exception as e:
                logger.error(f"Failed to write logout audit log: {e}")

        AuthService._current_user = None
