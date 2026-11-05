"""
Cash Drawer Service — manages manual cash drawer openings and auditing (#793).
"""

import json
import logging

from cbpos.core.database import Database
from cbpos.core.models import AuditLog
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.shift_service import ShiftService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

logger = logging.getLogger(__name__)


class CashDrawerService:
    """Service to handle manual cash drawer kicks and compliance auditing."""

    @staticmethod
    def record_manual_open(
        user_id: int,
        approved_by_id: int | None = None,
        reason: str | None = None,
        terminal_id: str | None = None,
    ) -> None:
        """Record manual drawer open in AuditLog and queue drawer kick.

        Args:
            user_id: The cashier performing or requesting the open.
            approved_by_id: The manager who approved the override (if different from user_id).
            reason: Optional explanation.
            terminal_id: Optional terminal identifier.
        """
        if not terminal_id:
            terminal_id = ConfigService.get("terminal_id") or "TERM-01"

        shift = ShiftService().get_current_shift(user_id, terminal_id)
        shift_id = shift.id if shift else None

        details_dict = {
            "shift_id": shift_id,
            "approved_by_id": approved_by_id,
        }
        if reason:
            details_dict["reason"] = reason

        details_str = json.dumps(details_dict)

        db = Database()
        try:
            with db.get_session() as session:
                log = AuditLog(
                    user_id=user_id,
                    action="NO_SALE_DRAWER_OPEN",
                    event_type="SECURITY",
                    terminal_id=terminal_id,
                    details=details_str,
                )
                session.add(log)
        except Exception as e:
            logger.error("Failed to write manual drawer open audit log: %s", e)

        # Queue kick drawer job with manual: True so it bypasses drawer_on_cash_only
        PrintWorker.instance().add_job("kick_drawer", {"manual": True})
