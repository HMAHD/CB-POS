from cbpos.core.database import Database
from cbpos.core.models import AuditLog


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
        # Use a fresh session to ensure log is committed independently of main transaction
        session = db.SessionLocal()
        try:
            log = AuditLog(user_id=user_id, action=action, details=details)
            session.add(log)
            session.commit()
        except Exception as e:
            print(f"Failed to write audit log: {e}")
            session.rollback()
        finally:
            session.close()
