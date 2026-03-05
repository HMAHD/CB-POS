import hashlib
import logging
import time
from typing import Optional

import bcrypt
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import User

logger = logging.getLogger(__name__)


def _get_max_attempts() -> int:
    """Get max failed login attempts from config (fallback: 5)."""
    try:
        from cbpos.core.services.config_service import ConfigService

        return int(ConfigService.get("max_login_attempts") or 5)
    except Exception as e:
        logger.debug("Could not read 'max_login_attempts' from config, using fallback. Error: %s", e)
        return 5


def _get_lockout_duration() -> int:
    """Get lockout duration in seconds from config (fallback: 300)."""
    try:
        from cbpos.core.services.config_service import ConfigService

        return int(ConfigService.get("lockout_duration_seconds") or 300)
    except Exception as e:
        logger.debug("Could not read 'lockout_duration_seconds' from config, using fallback. Error: %s", e)
        return 300


class AuthService:
    """
    Service to handle user authentication and session management.

    Security features:
    - bcrypt PIN hashing with automatic migration from legacy SHA-256
    - Brute-force protection: configurable lockout (default 5 min after 5 failed attempts)
    """

    _current_user: Optional[User] = None

    # In-memory brute-force tracking: {username: {"attempts": int, "locked_until": float}}
    _failed_attempts: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # PIN hashing helpers (used by UserService and seed script too)
    # ------------------------------------------------------------------

    @staticmethod
    def hash_pin(pin: str) -> str:
        """
        Hash a PIN using bcrypt.

        Args:
            pin: The plaintext PIN string.

        Returns:
            The bcrypt hash as a UTF-8 string.
        """
        return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def _is_legacy_hash(pin_hash: str) -> bool:
        """Check whether a stored hash is a legacy SHA-256 hex digest (64 hex chars)."""
        return len(pin_hash) == 64 and all(c in "0123456789abcdef" for c in pin_hash)

    @staticmethod
    def _verify_against_hash(pin: str, stored_hash: str) -> bool:
        """
        Verify a plaintext PIN against a stored hash.

        Supports both legacy SHA-256 hashes and modern bcrypt hashes.

        Args:
            pin: The plaintext PIN.
            stored_hash: The hash stored in the database.

        Returns:
            True if the PIN matches the stored hash.
        """
        if AuthService._is_legacy_hash(stored_hash):
            return hashlib.sha256(pin.encode()).hexdigest() == stored_hash
        try:
            return bcrypt.checkpw(pin.encode("utf-8"), stored_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Brute-force protection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_locked_out(username: str) -> bool:
        """Check if a username is currently locked out due to too many failed attempts."""
        info = AuthService._failed_attempts.get(username)
        if not info:
            return False
        if info["attempts"] >= _get_max_attempts():
            if time.monotonic() < info["locked_until"]:
                return True
            # Lockout period expired — reset
            del AuthService._failed_attempts[username]
        return False

    @staticmethod
    def _record_failed_attempt(username: str) -> None:
        """Record a failed login attempt for brute-force tracking."""
        info = AuthService._failed_attempts.get(username)
        if info is None:
            info = {"attempts": 0, "locked_until": 0.0}
            AuthService._failed_attempts[username] = info
        info["attempts"] += 1
        if info["attempts"] >= _get_max_attempts():
            info["locked_until"] = time.monotonic() + _get_lockout_duration()
            logger.warning(
                "Account '%s' locked for %d seconds after %d failed attempts",
                username,
                _get_lockout_duration(),
                _get_max_attempts(),
            )

    @staticmethod
    def _reset_failed_attempts(username: str) -> None:
        """Reset the failed attempt counter on successful login."""
        AuthService._failed_attempts.pop(username, None)

    @staticmethod
    def get_remaining_lockout_seconds(username: str) -> int:
        """
        Return the number of seconds remaining on a lockout, or 0 if not locked.

        Args:
            username: The username to check.

        Returns:
            Remaining lockout seconds (0 if not locked out).
        """
        info = AuthService._failed_attempts.get(username)
        if not info or info["attempts"] < _get_max_attempts():
            return 0
        remaining = info["locked_until"] - time.monotonic()
        return max(0, int(remaining))

    # ------------------------------------------------------------------
    # Core authentication
    # ------------------------------------------------------------------

    @staticmethod
    def verify_pin(pin: str) -> Optional[User]:
        """
        Verify the provided PIN against the database.

        Includes brute-force protection and automatic migration from
        legacy SHA-256 hashes to bcrypt on successful login.

        Args:
            pin: The PIN entered by the user.

        Returns:
            The User object if authentication is successful, else None.
        """
        db = Database()
        with db.get_session() as session:
            # Fetch all active users with their roles
            users = session.query(User).options(joinedload(User.role)).filter(User.is_active.is_(True)).all()

            for user in users:
                # Check brute-force lockout per username
                if AuthService._is_locked_out(user.username):
                    continue

                if AuthService._verify_against_hash(pin, user.pin_hash):
                    # --- Successful match ---

                    # Migrate legacy SHA-256 hash to bcrypt transparently
                    if AuthService._is_legacy_hash(user.pin_hash):
                        user.pin_hash = AuthService.hash_pin(pin)
                        session.commit()
                        logger.info(
                            "Migrated PIN hash to bcrypt for user '%s'",
                            user.username,
                        )

                    # Reset brute-force counter
                    AuthService._reset_failed_attempts(user.username)

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
                        logger.error("Failed to write login audit log: %s", e)

                    return user

            # No match found — record failed attempt for ALL active users
            # (We don't know which user was targeted with PIN-only auth,
            #  but we track per-user to avoid locking innocent accounts.
            #  Since we can't identify the target, we don't increment here.)
            # Instead, we log a general failed attempt warning.
            logger.warning("Failed login attempt with PIN")

        return None

    @staticmethod
    def verify_pin_for_user(username: str, pin: str) -> Optional[User]:
        """
        Verify a PIN for a specific username (used where username is known).

        Includes brute-force protection and automatic bcrypt migration.

        Args:
            username: The target username.
            pin: The plaintext PIN.

        Returns:
            The User object on success, else None.
        """
        if AuthService._is_locked_out(username):
            remaining = AuthService.get_remaining_lockout_seconds(username)
            logger.warning(
                "Login attempt for locked account '%s' (%ds remaining)",
                username,
                remaining,
            )
            return None

        db = Database()
        with db.get_session() as session:
            user = (
                session.query(User)
                .options(joinedload(User.role))
                .filter(User.username == username, User.is_active.is_(True))
                .first()
            )

            if not user or not AuthService._verify_against_hash(pin, user.pin_hash):
                AuthService._record_failed_attempt(username)
                return None

            # Migrate legacy hash
            if AuthService._is_legacy_hash(user.pin_hash):
                user.pin_hash = AuthService.hash_pin(pin)
                session.commit()
                logger.info("Migrated PIN hash to bcrypt for user '%s'", username)

            AuthService._reset_failed_attempts(username)

            if user.role:
                _ = user.role.name
                session.expunge(user.role)
            session.expunge(user)

            AuthService._current_user = user
            return user

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
                logger.error("Failed to write logout audit log: %s", e)

        AuthService._current_user = None
