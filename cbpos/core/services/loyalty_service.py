"""
LoyaltyService: domain rules for earning, reversing, and tracking loyalty points.
"""

import json
import logging
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Customer, LoyaltyLedgerEntry, Sale
from cbpos.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


class LoyaltyService:
    """Service managing loyalty points earning, ledger recording, and reversals."""

    @staticmethod
    def calculate_points_earned(final_bill: Decimal, ratio: int | None = None) -> int:
        """Calculate whole loyalty points earned on a final bill amount.

        Points = floor(final_bill / ratio), earned only when loyalty is enabled.

        Args:
            final_bill: Final bill amount after all discounts and redemptions.
            ratio: Rupees spent per point earned (defaults to loyalty_points_ratio setting).

        Returns:
            Whole number of points earned (0 if disabled or amount is insufficient).
        """
        if not ConfigService.get("enable_loyalty"):
            return 0

        effective_ratio = int(ConfigService.get("loyalty_points_ratio") or 100) if ratio is None else int(ratio)
        if effective_ratio <= 0:
            return 0

        bill = Decimal(str(final_bill or 0))
        if bill <= Decimal("0"):
            return 0

        return int(bill // effective_ratio)

    @staticmethod
    def record_sale_points(session: Session, sale: Sale) -> LoyaltyLedgerEntry | None:
        """Award points on a completed sale within the caller's session/transaction.

        Args:
            session: Active SQLAlchemy session.
            sale: The completed sale document.

        Returns:
            The created LoyaltyLedgerEntry or None if no points were earned.
        """
        if not sale.customer_id:
            return None

        if not ConfigService.get("enable_loyalty"):
            return None

        final_bill = Decimal(str(sale.total_amount or 0))
        points = LoyaltyService.calculate_points_earned(final_bill)
        if points <= 0:
            return None

        customer = session.get(Customer, sale.customer_id, with_for_update=True)
        if not customer:
            logger.warning("record_sale_points: Customer %d not found", sale.customer_id)
            return None

        customer.loyalty_points = (customer.loyalty_points or 0) + points

        entry = LoyaltyLedgerEntry(
            customer_id=customer.id,
            entry_type="EARN",
            points=points,
            balance_after=customer.loyalty_points,
            reference_id=sale.id,
            note=f"Earned on sale {sale.document_number}",
        )
        session.add(entry)
        return entry

    @staticmethod
    def reverse_sale_points(session: Session, sale: Sale, reason: str = "VOID") -> LoyaltyLedgerEntry | None:
        """Reverse points earned on a sale within the caller's session/transaction.

        Capped at the points the sale originally earned. Never reverses twice, and
        never leaves the customer's balance below zero silently (clamps to 0 and logs warning).

        Args:
            session: Active SQLAlchemy session.
            sale: The sale being voided or refunded.
            reason: "VOID" or "REFUND".

        Returns:
            The created LoyaltyLedgerEntry or None if no points were reversed.
        """
        if not sale.customer_id:
            return None

        session.flush()

        earned = (
            session.query(func.coalesce(func.sum(LoyaltyLedgerEntry.points), 0))
            .filter(
                LoyaltyLedgerEntry.customer_id == sale.customer_id,
                LoyaltyLedgerEntry.reference_id == sale.id,
                LoyaltyLedgerEntry.entry_type == "EARN",
            )
            .scalar()
        )

        already_reversed = -(
            session.query(func.coalesce(func.sum(LoyaltyLedgerEntry.points), 0))
            .filter(
                LoyaltyLedgerEntry.customer_id == sale.customer_id,
                LoyaltyLedgerEntry.reference_id == sale.id,
                LoyaltyLedgerEntry.entry_type == "REVERSAL",
            )
            .scalar()
        )

        points_to_reverse = max(0, int(earned) - int(already_reversed))
        if points_to_reverse <= 0:
            return None

        customer = session.get(Customer, sale.customer_id, with_for_update=True)
        if not customer:
            logger.warning("reverse_sale_points: Customer %d not found", sale.customer_id)
            return None

        current_points = customer.loyalty_points or 0
        new_points = current_points - points_to_reverse

        if new_points < 0:
            logger.warning(
                "Loyalty reversal: customer %d points would drop below zero (%d - %d = %d); clamped to 0",
                customer.id,
                current_points,
                points_to_reverse,
                new_points,
            )
            customer.loyalty_points = 0
        else:
            customer.loyalty_points = new_points

        entry = LoyaltyLedgerEntry(
            customer_id=customer.id,
            entry_type="REVERSAL",
            points=-points_to_reverse,
            balance_after=customer.loyalty_points,
            reference_id=sale.id,
            note=f"{reason.title()} of {sale.document_number}",
        )
        session.add(entry)
        return entry

    @staticmethod
    def adjust_points(
        customer_id: int,
        points_delta: int,
        reason: str,
        user_id: int,
        session: Session | None = None,
    ) -> LoyaltyLedgerEntry:
        """Manually adjust a customer's loyalty points balance with an audited reason.

        Args:
            customer_id: ID of the customer.
            points_delta: Positive (add) or negative (remove) points change.
            reason: Required explanation for the manual adjustment.
            user_id: ID of the user performing the adjustment.
            session: Optional existing SQLAlchemy session. If None, manages its own transaction.

        Returns:
            The created LoyaltyLedgerEntry.

        Raises:
            ValueError: If reason is missing, delta is zero/invalid, or balance drops below zero.
        """
        if not reason or not reason.strip():
            raise ValueError("Adjustment reason is required.")

        if not isinstance(points_delta, int) or points_delta == 0:
            raise ValueError("Points adjustment must be a non-zero integer.")

        def _do_adjust(sess: Session) -> LoyaltyLedgerEntry:
            customer = sess.get(Customer, customer_id, with_for_update=True)
            if not customer:
                raise ValueError(f"Customer {customer_id} not found.")

            old_points = customer.loyalty_points or 0
            new_points = old_points + points_delta
            if new_points < 0:
                raise ValueError("Points adjustment cannot take customer balance below zero.")

            customer.loyalty_points = new_points

            entry = LoyaltyLedgerEntry(
                customer_id=customer.id,
                entry_type="ADJUSTMENT",
                points=points_delta,
                balance_after=new_points,
                reference_id=None,
                note=reason.strip(),
                synced=False,
            )
            sess.add(entry)

            effective_user_id = user_id
            if effective_user_id is None:
                from cbpos.core.services.auth_service import AuthService

                current_user = AuthService.get_current_user()
                if current_user:
                    effective_user_id = current_user.id

            if effective_user_id is not None:
                audit_details = json.dumps(
                    {
                        "customer": customer.name,
                        "old": old_points,
                        "new": new_points,
                        "points_delta": points_delta,
                        "reason": reason.strip(),
                    }
                )
                audit = AuditLog(
                    user_id=effective_user_id,
                    action="LOYALTY_ADJUSTMENT",
                    event_type="LOYALTY",
                    details=audit_details,
                )
                sess.add(audit)
            return entry

        if session is not None:
            return _do_adjust(session)

        with Database().get_session() as sess:
            entry = _do_adjust(sess)
            sess.commit()
            return entry

    @staticmethod
    def get_points_history(customer_id: int) -> list[LoyaltyLedgerEntry]:
        """Fetch all loyalty ledger entries for a customer in reverse chronological order.

        Args:
            customer_id: ID of the customer.

        Returns:
            List of LoyaltyLedgerEntry ordered by timestamp descending, id descending.
        """
        with Database().get_session() as session:
            return (
                session.query(LoyaltyLedgerEntry)
                .filter_by(customer_id=customer_id)
                .order_by(LoyaltyLedgerEntry.timestamp.desc(), LoyaltyLedgerEntry.id.desc())
                .all()
            )
