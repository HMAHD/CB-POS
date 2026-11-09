"""
FIFO debt and payable aging calculation (Issues #883, #897).

Matches charges against credits in chronological order.
Unpaid remainder preserves the original charge's age.
"""

from collections import deque
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def oldest_open_charge(
    entries: Iterable[Any],
    charge_types: set[str] | tuple[str, ...] | None = None,
    credit_types: set[str] | tuple[str, ...] | None = None,
) -> date | None:
    """Find the date of the oldest open (unpaid) charge using FIFO allocation.

    Args:
        entries: Chronologically sorted ledger entries (CustomerLedgerEntry or SupplierLedgerEntry).
        charge_types: Optional set of entry types considered charges.
        credit_types: Optional set of entry types considered credits.

    Returns:
        date of the oldest charge that still has an unpaid balance, or None if all charges are settled.
    """
    queue: deque[dict[str, Any]] = deque()
    unallocated_credit = Decimal("0")

    for entry in entries:
        amt = getattr(entry, "amount", None)
        if amt is None:
            continue
        amt = Decimal(str(amt))
        if amt == 0:
            continue

        etype = getattr(entry, "entry_type", None)

        is_charge = (amt > 0) and (charge_types is None or etype in charge_types)
        is_credit = (amt < 0) and (credit_types is None or etype in credit_types)

        ts = getattr(entry, "timestamp", None)
        if isinstance(ts, datetime):
            entry_date = ts.date()
        elif isinstance(ts, date):
            entry_date = ts
        else:
            raise ValueError(f"Ledger entry {entry!r} has invalid timestamp: {ts!r}")

        if is_charge:
            charge_rem = amt
            if unallocated_credit > 0:
                if unallocated_credit >= charge_rem:
                    unallocated_credit -= charge_rem
                    charge_rem = Decimal("0")
                else:
                    charge_rem -= unallocated_credit
                    unallocated_credit = Decimal("0")

            if charge_rem > 0:
                queue.append({"date": entry_date, "remaining": charge_rem})

        elif is_credit:
            credit_rem = abs(amt)
            while queue and credit_rem > 0:
                head = queue[0]
                if head["remaining"] <= credit_rem:
                    credit_rem -= head["remaining"]
                    queue.popleft()
                else:
                    head["remaining"] -= credit_rem
                    credit_rem = Decimal("0")

            if credit_rem > 0:
                unallocated_credit += credit_rem

    if queue:
        return queue[0]["date"]
    return None
