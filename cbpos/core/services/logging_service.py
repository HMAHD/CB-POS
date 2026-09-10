import logging

from cbpos.core.database import Database
from cbpos.core.models import AuditLog

logger = logging.getLogger(__name__)


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
