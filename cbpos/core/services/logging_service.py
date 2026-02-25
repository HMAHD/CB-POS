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
    def log_action(user_id: int, action: str, details: str = None):
        """
        Log a critical action to the database.

        Args:
            user_id (int): ID of the user performing the action.
            action (str): Short description of the action (e.g., 'VOID_SALE').
            details (str): Additional details (optional).
        """
        db = Database()
        try:
            with db.get_session() as session:
                log = AuditLog(user_id=user_id, action=action, details=details)
                session.add(log)
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)
