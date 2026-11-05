"""
Money and precision utilities.

Implements approved rounding helpers (D4) using ROUND_HALF_UP and fixed precision.
"""

from decimal import ROUND_HALF_UP, Decimal

from cbpos.core.constants.status import Precision


def round_money(val: Decimal | str | float | int) -> Decimal:
    """Round a monetary amount to 2 decimal places using ROUND_HALF_UP (D4)."""
    return Decimal(str(val)).quantize(Precision.MONEY, rounding=ROUND_HALF_UP)


def round_qty(val: Decimal | str | float | int) -> Decimal:
    """Round a quantity value to 3 decimal places using ROUND_HALF_UP."""
    return Decimal(str(val)).quantize(Precision.QUANTITY, rounding=ROUND_HALF_UP)
