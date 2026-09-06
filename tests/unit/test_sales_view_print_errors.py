"""
Tests that SalesView surfaces a print failure to the cashier for the
"frictionless" auto-print path (show_receipt_dialog off), not just for
the cash drawer.

TransactionService._print_receipt_async() (called from _execute_sale()
only when show_receipt_dialog is off) queues the receipt print job via
PrintWorker.instance().add_job(...) and returns -- there's no dialog open
at that point to react synchronously (that's the point of "frictionless"),
so before this fix there was no connection to error_occurred anywhere in
that path, unlike open_cash_drawer() right next to it in the same
_execute_sale() transaction. A cashier had zero indication a receipt
silently failed to print. Fixed by connecting once, for the view's whole
lifetime, in SalesView.__init__ -- covering both the drawer and any other
job PrintWorker.instance() (shared across the whole app) ever queues.
"""

from unittest.mock import patch

import pytest

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


class TestAutoPrintErrorsReachTheCashier:
    def test_error_from_any_queued_job_shows_a_warning(self, view):
        """Simulates TransactionService._print_receipt_async() failing --
        no dialog is open, just SalesView's own permanent connection."""
        with patch("cbpos.ui.views.sales_view.QMessageBox") as mock_box:
            PrintWorker.instance().error_occurred.emit("Printer not available.")
            mock_box.warning.assert_called_once()

    def test_open_cash_drawer_still_reports_exactly_one_error(self, view):
        with patch.object(PrintWorker, "add_job"), patch("cbpos.ui.views.sales_view.QMessageBox") as mock_box:
            for _ in range(3):  # F8 pressed multiple times in a session
                view.open_cash_drawer()

            PrintWorker.instance().error_occurred.emit("Printer not available.")
            mock_box.warning.assert_called_once()
