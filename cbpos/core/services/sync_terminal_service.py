"""Service for managing registered sync terminals."""

import logging
from typing import Any

from cbpos.core.database import Database
from cbpos.core.models import SyncTerminal
from cbpos.core.services.logging_service import LoggingService

logger = logging.getLogger(__name__)


class SyncTerminalService:
    """Service to query and manage LAN sync terminals registered on the Main PC."""

    @staticmethod
    def count_active_terminals(window_minutes: int = 5) -> int:
        """Count distinct terminals seen in the last window_minutes that are not released (#906)."""
        from datetime import datetime, timedelta

        from sqlalchemy import func

        try:
            cutoff = datetime.now() - timedelta(minutes=window_minutes)
            db = Database()
            with db.get_session() as session:
                count = (
                    session.query(func.count(SyncTerminal.terminal_id))
                    .filter(
                        SyncTerminal.last_seen >= cutoff,
                        SyncTerminal.released.is_(False),
                    )
                    .scalar()
                )
                return count or 0
        except Exception as e:
            logger.warning("Could not count active sync terminals: %s", e)
            return 0

    @staticmethod
    def list_terminals() -> list[dict[str, Any]]:
        """Return all registered terminals ordered by terminal_id."""
        try:
            db = Database()
            with db.get_session() as session:
                rows = session.query(SyncTerminal).order_by(SyncTerminal.terminal_id.asc()).all()
                return [
                    {
                        "terminal_id": r.terminal_id,
                        "db_instance_id": r.db_instance_id,
                        "first_seen": r.first_seen,
                        "last_seen": r.last_seen,
                        "last_ip": r.last_ip,
                        "released": bool(r.released),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning("Could not list sync terminals: %s", e)
            return []

    @staticmethod
    def release_terminal(terminal_id: str, user_id: int | None = None) -> bool:
        """Mark a terminal ID as released, allowing another machine or new database instance to claim it.

        Args:
            terminal_id: Terminal ID to release.
            user_id: ID of the admin user releasing the ID (for audit logging).

        Returns:
            True if terminal was found and released, False if not found.
        """
        db = Database()
        with db.get_session() as session:
            terminal = session.query(SyncTerminal).filter_by(terminal_id=terminal_id).first()
            if not terminal:
                return False
            terminal.released = True
            session.commit()

        LoggingService.log_action(
            user_id=user_id or 1,
            action="SYNC_TERMINAL_RELEASED",
            event_type="SECURITY",
            details=f"Released terminal ID '{terminal_id}'",
        )
        logger.info("Terminal %s released by user_id %s", terminal_id, user_id)
        return True
