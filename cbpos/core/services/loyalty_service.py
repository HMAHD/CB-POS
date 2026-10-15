"""
LoyaltyService: domain rules for earning, reversing, and tracking loyalty points.
"""

import logging
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from cbpos.core.models import Customer, LoyaltyLedgerEntry, Sale
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
