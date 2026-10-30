import hashlib
import logging
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import Role, User

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
    """Service to handle user authentication and session management.

    Security features:

    - bcrypt PIN hashing with automatic migration from legacy SHA-256
    - Database-backed brute-force protection: configurable lockout
      (default 5 min after 5 failed attempts), persists across restarts
      and is shared across all terminals in network mode.
    """

    _current_user: User | None = None

    # ------------------------------------------------------------------
    # PIN hashing helpers (used by UserService and seed script too)
    # ------------------------------------------------------------------

    @staticmethod
    def hash_pin(pin: str) -> str:
        """Hash a PIN using bcrypt.

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
        """Verify a plaintext PIN against a stored hash.

        Supports both legacy SHA-256 hashes and modern bcrypt hashes.
        """
        if AuthService._is_legacy_hash(stored_hash):
            return hashlib.sha256(pin.encode()).hexdigest() == stored_hash
        try:
            return bcrypt.checkpw(pin.encode("utf-8"), stored_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Database-backed brute-force protection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_locked_out_db(user: User) -> bool:
        """Check if a user is currently locked out based on DB columns."""
        return bool(user.locked_until and user.locked_until > datetime.now())

    @staticmethod
    def _record_failed_attempt_db(session, user: User) -> None:
        """Increment failed attempt counter and lock if threshold reached."""
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        max_attempts = _get_max_attempts()
        if user.failed_login_attempts >= max_attempts:
            duration = _get_lockout_duration()
            user.locked_until = datetime.now() + timedelta(seconds=duration)
            logger.warning(
                "Account '%s' locked for %d seconds after %d failed attempts",
                user.username,
                duration,
                max_attempts,
            )
        session.commit()

    @staticmethod
    def _reset_failed_attempts_db(session, user: User) -> None:
        """Reset the failed attempt counter on successful login."""
        if user.failed_login_attempts or user.locked_until:
            user.failed_login_attempts = 0
            user.locked_until = None
            session.flush()

    @staticmethod
    def get_remaining_lockout_seconds(username: str) -> int:
        """Return the number of seconds remaining on a lockout, or 0 if not locked.

        Args:
            username: The username to check.

        Returns:
            Remaining lockout seconds (0 if not locked out).
        """
        db = Database()
        with db.get_session() as session:
            user = session.query(User).filter(User.username == username).first()
            if not user or not user.locked_until:
                return 0
            remaining = (user.locked_until - datetime.now()).total_seconds()
            return max(0, int(remaining))

    # ------------------------------------------------------------------
    # Core authentication
    # ------------------------------------------------------------------

    @staticmethod
    def _match_active_user(session, pin: str) -> User | None:
        """Find an active user matching the given PIN and handle hash migration.

        Eagerly loads role and permissions, and expunges the user and its
        role before returning so the detached object can be used safely
        after the session closes.
        """
        users = (
            session.query(User)
            .options(joinedload(User.role).joinedload(Role.permissions))
            .filter(User.is_active.is_(True))
            .all()
        )

        matched_user = None
        for user in users:
            # Check database-backed lockout
            if AuthService._is_locked_out_db(user):
                continue

            if AuthService._verify_against_hash(pin, user.pin_hash):
                matched_user = user
                break

        if not matched_user:
            logger.warning("Failed authentication attempt with PIN")
            return None

        # --- Successful match ---

        # Migrate legacy SHA-256 hash to bcrypt transparently
        if AuthService._is_legacy_hash(matched_user.pin_hash):
            matched_user.pin_hash = AuthService.hash_pin(pin)
            logger.info("Migrated PIN hash to bcrypt for user '%s'", matched_user.username)

        # Reset brute-force counter
        AuthService._reset_failed_attempts_db(session, matched_user)

        # Detach user and role to keep available after session close
        if matched_user.role:
            _ = matched_user.role.name  # Force load
            _ = list(matched_user.role.permissions)
            for perm in matched_user.role.permissions:
                _ = perm.code
                session.expunge(perm)
            session.expunge(matched_user.role)
        session.expunge(matched_user)

        return matched_user

    @staticmethod
    def login(pin: str) -> User | None:
        """Verify the provided PIN against the database and log the user in.

        Sets `_current_user`, writes a LOGIN audit log, and checks for concurrent sessions.
        Includes brute-force protection and automatic migration from
        legacy SHA-256 hashes to bcrypt on successful login.

        Args:
            pin: The PIN entered by the user.

        Returns:
            The User object if authentication is successful, else None.
        """
        db = Database()
        with db.get_session() as session:
            user = AuthService._match_active_user(session, pin)
            if not user:
                return None

            AuthService._current_user = user

            # Log login and check for concurrent sessions
            try:
                from cbpos.core.models import AuditLog
                from cbpos.core.services.config_service import ConfigService

                terminal_id = ConfigService.get("terminal_id") or "TERM-01"

                # Warn if user is already logged in on another terminal
                # (check audit log for LOGIN without matching LOGOUT)
                last_login = (
                    session.query(AuditLog)
                    .filter(
                        AuditLog.user_id == user.id,
                        AuditLog.event_type == "LOGIN",
                        AuditLog.terminal_id != terminal_id,
                    )
                    .order_by(AuditLog.timestamp.desc())
                    .first()
                )
                if last_login:
                    # Check if there's a logout after it
                    last_logout = (
                        session.query(AuditLog)
                        .filter(
                            AuditLog.user_id == user.id,
                            AuditLog.event_type == "LOGOUT",
                            AuditLog.terminal_id == last_login.terminal_id,
                            AuditLog.timestamp > last_login.timestamp,
                        )
                        .first()
                    )
                    if not last_logout:
                        logger.warning(
                            "User '%s' may be logged in on terminal '%s' "
                            "(no logout recorded). Concurrent session detected.",
                            user.username,
                            last_login.terminal_id,
                        )

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
                session.rollback()
                logger.error("Failed to write login audit log: %s", e)

            return user

    verify_pin = login  # Deprecated alias for login(); callers should use login() or authenticate_pin()

    @staticmethod
    def authenticate_pin(pin: str) -> User | None:
        """Authenticate a user by PIN without altering the currently logged-in session.

        Used for manager overrides. Writes an OVERRIDE_AUTH audit log on success,
        recording which cashier's session was active at the time.

        Args:
            pin: The PIN entered by the authorizer.

        Returns:
            The User object if authentication is successful, else None.
        """
        db = Database()
        with db.get_session() as session:
            user = AuthService._match_active_user(session, pin)
            if not user:
                return None

            try:
                from cbpos.core.models import AuditLog
                from cbpos.core.services.config_service import ConfigService

                current_user = AuthService.get_current_user()
                cashier_desc = f"for {current_user.username}" if current_user else "for <none>"
                terminal_id = ConfigService.get("terminal_id") or "TERM-01"

                log = AuditLog(
                    user_id=user.id,
                    action="Manager Override Authenticated",
                    event_type="OVERRIDE_AUTH",
                    terminal_id=terminal_id,
                    details=cashier_desc,
                )
                session.add(log)
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error("Failed to write override audit log: %s", e)

            return user

    @staticmethod
    def check_own_pin(user_id: int, pin: str) -> bool:
        """Verify the PIN for a specific user without altering the active session.

        Used by ProfileDialog to confirm the user's current PIN.

        Args:
            user_id: ID of the user being verified.
            pin: The plaintext PIN to check.

        Returns:
            True if PIN matches and user is active, else False.
        """
        db = Database()
        with db.get_session() as session:
            user = session.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
            if not user:
                return False

            if AuthService._is_locked_out_db(user):
                return False

            return AuthService._verify_against_hash(pin, user.pin_hash)

    @staticmethod
    def is_pin_in_use(pin: str, exclude_user_id: int | None = None) -> bool:
        """Check whether a plaintext PIN is already in use by any active user.

        Args:
            pin: The plaintext PIN to check.
            exclude_user_id: Optional user ID to exclude (e.g. current user during edit).

        Returns:
            True if another active user matches this PIN, else False.
        """
        db = Database()
        with db.get_session() as session:
            query = session.query(User).filter(User.is_active.is_(True))
            if exclude_user_id is not None:
                query = query.filter(User.id != exclude_user_id)
            users = query.all()
            return any(AuthService._verify_against_hash(pin, user.pin_hash) for user in users)

    @staticmethod
    def verify_pin_for_user(username: str, pin: str) -> User | None:
        """Verify a PIN for a specific username (used where username is known).

        Includes brute-force protection and automatic bcrypt migration.

        Args:
            username: The target username.
            pin: The plaintext PIN.

        Returns:
            The User object on success, else None.
        """
        db = Database()
        with db.get_session() as session:
            user = (
                session.query(User)
                .options(joinedload(User.role).joinedload(Role.permissions))
                .filter(User.username == username, User.is_active.is_(True))
                .first()
            )

            if not user:
                return None

            # Check database-backed lockout
            if AuthService._is_locked_out_db(user):
                remaining = 0
                if user.locked_until:
                    remaining = max(0, int((user.locked_until - datetime.now()).total_seconds()))
                logger.warning(
                    "Login attempt for locked account '%s' (%ds remaining)",
                    username,
                    remaining,
                )
                return None

            if not AuthService._verify_against_hash(pin, user.pin_hash):
                AuthService._record_failed_attempt_db(session, user)
                return None

            # Migrate legacy hash
            if AuthService._is_legacy_hash(user.pin_hash):
                user.pin_hash = AuthService.hash_pin(pin)
                logger.info("Migrated PIN hash to bcrypt for user '%s'", username)

            AuthService._reset_failed_attempts_db(session, user)
            session.commit()

            if user.role:
                _ = user.role.name
                _ = list(user.role.permissions)
                for perm in user.role.permissions:
                    _ = perm.code
                    session.expunge(perm)
                session.expunge(user.role)
            session.expunge(user)

            AuthService._current_user = user
            return user

    @staticmethod
    def get_current_user() -> User | None:
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
            except Exception as e:
                logger.error("Failed to write logout audit log: %s", e)

        AuthService._current_user = None
