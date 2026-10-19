"""How a full refund splits into money handed back and credit given back (#715, #730).

A refund of a credit sale takes the credit part off the customer's debt, so
only the rest is handed back. ``refund_cash_back`` is the one place that rule
lives: the refund screens (via ``TransactionService.refund_breakdown``) and the
refund slip (``RefundReceiptBuilder``) both use it, so they can never disagree.
"""

from dataclasses import dataclass
from decimal import Decimal

ZERO_MONEY = Decimal("0.00")


def refund_cash_back(total: Decimal, credit_reversed: Decimal) -> Decimal:
    """Money handed back for a refund: the total less what comes off credit, never below zero.

    Args:
        total: Amount being refunded.
        credit_reversed: Part of it taken off the customer's credit instead.

    Returns:
        Amount the cashier hands back (0.00 for an all-credit sale).
    """
    return max(total - credit_reversed, ZERO_MONEY)


@dataclass(frozen=True, slots=True)
class RefundBreakdown:
    """The split the refund screens show before and after a full refund.

    Attributes:
        total: The sale's total.
        cash_back: Money handed back (see :func:`refund_cash_back`); 0.00 when
            the sale can't be refunded.
        credit_reversed: Credit taken off the customer's book; 0.00 when the
            sale can't be refunded.
        customer_name: The sale's customer, or "" for a walk-in.
    """

    total: Decimal
    cash_back: Decimal
    credit_reversed: Decimal
    customer_name: str = ""
