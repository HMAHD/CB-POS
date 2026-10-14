"""Saving Settings together with its Activity Log entry (#613, #729).

Only real changes are logged: values are compared numerically (Decimal), so a rate stored as
18.0 and saved back as 18 is not a change.
"""

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from cbpos.core.database import Database
from cbpos.core.models import AuditLog

logger = logging.getLogger(__name__)

# Settings whose changes go to the Activity Log
TAX_AUDIT_KEYS = ("tax_vat_rate", "tax_sscl_rate", "tax_sscl_turnover_pct", "vat_registered")


def _comparable(value: Any) -> Any:
    """Bools stay bools; numbers (int/float/numeric str) become Decimal; anything else as-is."""
    if value is None or isinstance(value, bool):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value


class SettingsAuditService:
    """Writes Activity Log rows for audited Settings changes."""

    @staticmethod
    def tax_changes(old_config: dict, new_settings: dict) -> dict:
        """Return {key: {"old": ..., "new": ...}} for audited tax settings that really changed.

        Args:
            old_config: Settings before the save.
            new_settings: Settings being saved; keys it doesn't contain are not compared.

        Returns:
            dict: The changed keys, with their raw old/new values.
        """
        changes = {}
        for key in TAX_AUDIT_KEYS:
            if key not in new_settings or new_settings[key] is None:
                continue
            old, new = old_config.get(key), new_settings[key]
            if _comparable(old) != _comparable(new):
                changes[key] = {"old": old, "new": new}
        return changes

    @classmethod
    def save_settings(cls, new_settings: dict, user_id: int | None = None, terminal_id: str | None = None) -> bool:
        """Save Settings and write their TAX_RATE_CHANGE audit row as one change (#729).

        Settings live in settings.json, not the database, so the file write and the audit row
        can't share one database transaction. The order makes them behave as one:

        1. The audit row is added and flushed in an open session -- a database problem shows up
           here, before anything is saved.
        2. The settings file is written. If that fails, ``ConfigService`` puts the old values
           back and raises, and the session rolls back: no settings change, no audit row.
        3. The session commits only after the file was saved.

        That leaves one narrow case: the file is saved but the final commit fails. The settings
        then stand without their audit row (logged as an error). The other order would leave an
        audit row for a change that never happened, which is the bug this fixes.

        Details are stored as raw JSON; the Activity Log formats them at display time.

        Args:
            new_settings: Settings being saved.
            user_id: Who saved; defaults to the signed-in user (no row is written without a user).
            terminal_id: Terminal the save came from; defaults to this terminal.

        Returns:
            bool: True if an audit row was written.

        Raises:
            Exception: The settings could not be saved; nothing was changed or logged.
        """
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.config_service import ConfigService

        if user_id is None:
            user = AuthService.get_current_user()
            user_id = user.id if user else None
        terminal_id = terminal_id or ConfigService.get("terminal_id") or "TERM-01"
        changes = cls.tax_changes(ConfigService.get_all(), new_settings)
        audited = bool(changes) and user_id is not None

        saved = False
        try:
            with Database().get_session() as session:
                if audited:
                    session.add(
                        AuditLog(
                            user_id=user_id,
                            action="TAX_RATE_CHANGE",
                            event_type="SECURITY",
                            terminal_id=terminal_id,
                            details=json.dumps(changes),
                        )
                    )
                    session.flush()
                ConfigService.update_all(new_settings, raise_errors=True)
                saved = True
        except Exception:
            if not saved:
                raise
            logger.exception("Settings were saved but their audit entry could not be written")
            return False
        return audited
