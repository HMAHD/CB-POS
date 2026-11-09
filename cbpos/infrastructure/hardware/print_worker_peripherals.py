"""Production transaction peripherals: the shop's receipt printer and cash drawer (#733).

Every hardware rule for a committed sale or refund lives here, on top of
the shared ``PrintWorker`` thread, so ``TransactionService`` only says what
happened. Installed once by ``main()``.
"""

import logging

from cbpos.core.interfaces.transaction_peripherals import RefundCompleted, SaleCompleted
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.printer_service import PrinterService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

logger = logging.getLogger(__name__)


class PrintWorkerPeripherals:
    """Receipt, A4 invoice and cash drawer through the shared print worker.

    A sale:
        1. Auto-prints its receipt -- unless ``show_receipt_dialog`` is on,
           in which case the Receipt Options dialog prints it on request.
           ``PrinterService.print_transaction`` applies auto-print, copies,
           the receipt language and the extra A4 Tax Invoice for a
           VAT-registered customer.
        2. Then opens the drawer, passing the payment methods so the worker
           can keep it shut for a sale with no cash (``drawer_on_cash_only``).

    Both jobs go on the one worker queue, so the receipt always comes out
    before the drawer opens. A receipt that fails to build is logged and
    the drawer still opens -- the cashier still has change to give.

    A refund auto-prints its voucher (auto-print and copies apply); no drawer.
    """

    def sale_completed(self, event: SaleCompleted) -> None:
        """Print the receipt (unless the dialog will), then kick the drawer.

        Args:
            event: The committed sale and its payment methods.
        """
        if not ConfigService.get("show_receipt_dialog"):
            try:
                PrinterService.print_transaction(event.sale)
            except Exception as e:
                logger.error("Auto-print of %s failed: %s", event.sale.document_number, e)

        if event.sale.customer and getattr(event.sale.customer, "vat_number", None):
            if PrinterService._resolve_a4_printer():
                PrintWorker.instance().add_job("a4_invoice", event.sale.id)

        from cbpos.core.services.payment_service import classify_method_name

        method_kinds = [classify_method_name(m) for m in event.payment_methods]
        PrintWorker.instance().add_job("kick_drawer", {"manual": False, "method_kinds": method_kinds})

    def refund_completed(self, event: RefundCompleted) -> None:
        """Auto-print the refund voucher, if there is one.

        Args:
            event: The committed refund and its voucher commands.
        """
        if event.voucher:
            PrinterService.auto_print(event.voucher)
