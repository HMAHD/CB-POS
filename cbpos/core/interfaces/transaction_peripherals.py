"""Port between a committed transaction and the shop's hardware (#733).

The transaction service tells the port *what happened* -- a sale or a
refund was committed -- and the installed adapter decides what the
hardware does about it (receipt, A4 invoice, cash drawer). The service is
only ever told about a transaction once it is safely in the database, so a
failed commit can never print a receipt or open the drawer.

Adapters:
    - ``NullPeripherals`` (here): the headless default; does nothing.
    - ``PrintWorkerPeripherals`` (``cbpos.infrastructure.hardware``): the
      production adapter, installed once by ``main()``.
    - ``RecordingPeripherals`` (``tests/fakes.py``): records events for tests.

No Qt here: the core must run headless.
"""

import logging
import sys
from dataclasses import dataclass
from typing import Protocol

from cbpos.core.models import Sale

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SaleCompleted:
    """A sale was committed.

    Attributes:
        sale: The committed sale, detached, with what the receipt needs
            loaded (lines + products, payments, cashier, customer).
        payment_methods: The sale's payment method codes, in payment order
            (e.g. ``("CASH", "CARD")``) -- the drawer opens on cash only
            when the shop says so.
    """

    sale: Sale
    payment_methods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RefundCompleted:
    """A refund was committed.

    Attributes:
        refund_sale: The committed refund (credit note) document.
        voucher: The refund voucher's receipt commands, or None if there
            is nothing to print.
    """

    refund_sale: Sale
    voucher: list[dict] | None


class TransactionPeripherals(Protocol):
    """What the hardware does after a transaction is committed.

    Called only after the commit succeeded, never inside the database
    session. An adapter may raise; the caller logs the error and still
    reports the transaction as done, because it is.
    """

    def sale_completed(self, event: SaleCompleted) -> None:
        """React to a committed sale (receipt, invoice, drawer)."""
        ...

    def refund_completed(self, event: RefundCompleted) -> None:
        """React to a committed refund (refund voucher)."""
        ...


def _has_gui() -> bool:
    """Whether a Qt application is running, checked without importing Qt."""
    widgets = sys.modules.get("PyQt6.QtWidgets")
    return widgets is not None and widgets.QApplication.instance() is not None


class NullPeripherals:
    """Headless default: no hardware, nothing happens.

    In the real app (frozen build, or a GUI running) reaching this adapter
    means ``main()`` forgot to install the production one, so the first
    event logs a warning -- otherwise receipts would just silently stop.
    """

    def __init__(self) -> None:
        self._warned = False

    def _note(self, what: str, document_number: str | None) -> None:
        logger.debug("No peripherals installed -- %s %s: nothing printed.", what, document_number)
        if self._warned or not (getattr(sys, "frozen", False) or _has_gui()):
            return
        self._warned = True
        logger.warning(
            "No transaction peripherals installed: receipts and the cash drawer are off. "
            "Install one with TransactionService.use_peripherals()."
        )

    def sale_completed(self, event: SaleCompleted) -> None:
        """Do nothing (see class docstring)."""
        self._note("sale", event.sale.document_number)

    def refund_completed(self, event: RefundCompleted) -> None:
        """Do nothing (see class docstring)."""
        self._note("refund", event.refund_sale.document_number)
