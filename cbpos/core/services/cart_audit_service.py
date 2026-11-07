"""Audit service for cart line actions, notably quantity reductions (#893)."""

import json
from decimal import Decimal

from cbpos.core.services.logging_service import LoggingService


class CartAuditService:
    """Service to record audit logs for critical cart mutations."""

    @staticmethod
    def record_line_reduction(
        product_id: int,
        from_qty: Decimal,
        to_qty: Decimal,
        user_id: int | None,
        approver_id: int | None = None,
        product_name: str = "",
    ) -> None:
        """Record a LINE_QTY_REDUCED entry in AuditLog.

        Contains before/after quantities, actor (cashier) and approver (manager).
        """
        details = json.dumps(
            {
                "product_id": product_id,
                "product_name": product_name,
                "from_qty": str(from_qty),
                "to_qty": str(to_qty),
                "actor_id": user_id,
                "approver_id": approver_id,
            }
        )
        log_user_id = user_id or approver_id
        LoggingService.log_action(
            user_id=log_user_id,
            action="LINE_QTY_REDUCED",
            event_type="TRANSACTION",
            details=details,
        )
