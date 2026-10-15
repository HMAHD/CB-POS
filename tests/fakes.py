"""Test adapters shared across the suite."""

from cbpos.core.interfaces.transaction_peripherals import RefundCompleted, SaleCompleted


class RecordingPeripherals:
    """Transaction peripherals that record every event instead of touching hardware.

    Installed for every test by ``tests/conftest.py`` (fixture
    ``peripherals``), so a sale test asserts on ``.events`` rather than
    patching the print worker.
    """

    def __init__(self) -> None:
        self.events: list[SaleCompleted | RefundCompleted] = []

    def sale_completed(self, event: SaleCompleted) -> None:
        """Record the sale event."""
        self.events.append(event)

    def refund_completed(self, event: RefundCompleted) -> None:
        """Record the refund event."""
        self.events.append(event)
