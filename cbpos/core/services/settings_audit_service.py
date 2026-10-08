"""Audit logging for Settings saves (#613).

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
    def log_tax_changes(cls, old_config: dict, new_settings: dict, user_id: int | None, terminal_id: str) -> bool:
        """Write one TAX_RATE_CHANGE row if any audited tax setting really changed.

        Details are stored as raw JSON; the Activity Log formats them at display time.

        Args:
            old_config: Settings before the save.
            new_settings: Settings being saved.
            user_id: Who saved (no row is written without a user).
            terminal_id: Terminal the save came from.

        Returns:
            bool: True if a row was written.
        """
        changes = cls.tax_changes(old_config, new_settings)
        if not changes or user_id is None:
            return False
        try:
            with Database().get_session() as session:
                session.add(
                    AuditLog(
                        user_id=user_id,
                        action="TAX_RATE_CHANGE",
                        event_type="SECURITY",
                        terminal_id=terminal_id,
                        details=json.dumps(changes),
                    )
                )
            return True
        except Exception as e:
            logger.warning("Tax audit log failed: %s", e)
            return False
