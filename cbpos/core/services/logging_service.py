import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from cbpos.core.database import Database
from cbpos.core.models import AuditLog

logger = logging.getLogger(__name__)


def audit_value(value: Any) -> Any:
    """JSON-safe form of a value for an audit detail: Decimal -> "95.00", datetime -> "2026-10-14T09:00".

    Args:
        value: Any field value being audited.

    Returns:
        A string for Decimal, datetime and date values; anything else unchanged.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    return value


def diff_changes(old: dict[str, Any], new: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{field: {"old": x, "new": y}} for the fields whose audit value differs.

    Decimals compare by value, so 95 and 95.00 are not a change.

    Args:
        old: Field values before the change (missing keys count as None).
        new: Field values after the change.

    Returns:
        dict: Only the fields that really changed, as JSON-safe values.
    """
    changes = {}
    for key in dict.fromkeys([*old, *new]):  # field order as given, for a readable log
        before, after = old.get(key), new.get(key)
        if isinstance(before, Decimal) and isinstance(after, Decimal):
            if before == after:
                continue
        elif audit_value(before) == audit_value(after):
            continue
        changes[key] = {"old": audit_value(before), "new": audit_value(after)}
    return changes


def snapshot_changes(fields: dict[str, Any], deleted: bool = False) -> dict[str, dict[str, Any]]:
    """Every field as a change from nothing (created) or to nothing (``deleted=True``).

    Unlike :func:`diff_changes`, None values are kept: for some fields None has a meaning
    (a promotion with no days runs every day).

    Args:
        fields: Field values of the created or deleted record.
        deleted: True when the record was deleted (values go in "old"), False when created.

    Returns:
        dict: ``{field: {"old": x, "new": y}}`` with JSON-safe values for every field.
    """
    return {
        key: {"old": audit_value(value), "new": None} if deleted else {"old": None, "new": audit_value(value)}
        for key, value in fields.items()
    }


class LoggingService:
    """
    Service to handle audit logging.
    Writes logs in a separate session to ensure persistence.
    """

    @staticmethod
    def log_action(user_id: int, action: str, event_type: str, details: str = None):
        """
        Log a critical action to the database.

        Args:
            user_id (int): ID of the user performing the action.
            action (str): Short description of the action (e.g., 'VOID_SALE').
            event_type (str): Category shown in the Activity Log (e.g. 'INVENTORY',
                'SECURITY', 'TRANSACTION') -- required, since AuditLog.event_type
                is a non-nullable column and omitting it raises IntegrityError.
            details (str): Additional details (optional).
        """
        db = Database()
        try:
            with db.get_session() as session:
                log = AuditLog(user_id=user_id, action=action, event_type=event_type, details=details)
                session.add(log)
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)

    @staticmethod
    def add_change(
        session: Session,
        action: str,
        event_type: str,
        subject: str,
        changes: dict[str, dict[str, Any]],
        **context: Any,
    ) -> bool:
        """Add an Activity Log row for a data change to the caller's session (#642).

        The row is committed (or rolled back) together with the change itself. Details are
        stored as JSON ``{"subject": ..., "changes": {field: {"old", "new"}}, **context}`` and
        turned into readable, translated text by ``audit_format`` at display time.

        Args:
            session: The open session holding the change.
            action: Action code, e.g. "PRICE_LIST_UPDATE".
            event_type: Activity Log category, e.g. "PRICING".
            subject: What changed, as shown to people (a price list or promotion name).
            changes: Output of :func:`diff_changes`; nothing is written when it's empty.
            **context: Extra display context, e.g. ``item="Sugar 1kg"`` or ``value_type="PERCENTAGE"``.

        Returns:
            bool: True if a row was added (needs a signed-in user and at least one change).
        """
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.config_service import ConfigService

        user = AuthService.get_current_user()
        if user is None or not changes:
            return False
        details = {"subject": subject, "changes": changes}
        details.update({k: audit_value(v) for k, v in context.items() if v is not None})
        session.add(
            AuditLog(
                user_id=user.id,
                action=action,
                event_type=event_type,
                terminal_id=ConfigService.get("terminal_id") or "TERM-01",
                details=json.dumps(details, ensure_ascii=False),
            )
        )
        return True
