import logging
import os
import re
import tempfile
from typing import Any

from cbpos.core.models import Sale
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

logger = logging.getLogger(__name__)

_MAX_COPIES = 5  # Settings > Hardware caps receipt copies at 5


class PrinterService:
    """
    Single entry point for printing sale receipts.

    Every receipt print (auto after sale/refund, Receipt Options -> Print,
    reprints) builds its commands with `ReceiptBuilder` -- the same
    commands the Settings preview renders -- and queues them on the shared
    `PrintWorker` thread. VAT-registered customers additionally get an
    A4 Tax Invoice.

    Sinhala/Tamil: the builder emits receipt labels in the receipt
    language as plain text commands; the driver sends them as text, so
    the printed glyphs depend on the printer's code pages (see
    ``ESCPOSDriver.print_commands``).
    """

    @staticmethod
    def receipt_copies() -> int:
        """Return the configured number of receipt copies (1-5)."""
        try:
            copies = int(ConfigService.get("receipt_copies") or 1)
        except (TypeError, ValueError):
            return 1
        return min(max(copies, 1), _MAX_COPIES)

    @staticmethod
    def queue_commands(commands: list[dict[str, Any]], copies: int = 1) -> None:
        """Queue *copies* receipts as ONE print job on the shared PrintWorker.

        One job (not one per copy) so screens waiting on the worker's
        job_completed/error_occurred hear about the print exactly once.
        Each copy ends with the builder's own feed + cut.
        """
        copies = max(int(copies), 1)
        job = [cmd for _ in range(copies) for cmd in commands]
        PrintWorker.instance().add_job("print_receipt", job)
        logger.info("[PrinterService] Queued receipt job (%d cop%s)", copies, "y" if copies == 1 else "ies")

    @staticmethod
    def auto_print(commands: list[dict[str, Any]]) -> bool:
        """Automatic print after a sale/refund: honors auto_print_receipt and receipt_copies.

        Returns:
            True if a job was queued, False if auto-print is switched off.
        """
        if not ConfigService.get("auto_print_receipt"):
            logger.info("[PrinterService] Auto-print off -- receipt not printed")
            return False
        PrinterService.queue_commands(commands, PrinterService.receipt_copies())
        return True

    @staticmethod
    def print_transaction(sale: Sale, is_reprint: bool = False) -> bool:
        """Automatic receipt print for a completed sale.

        Builds the receipt with `ReceiptBuilder` (the same commands the
        Settings preview shows) and queues it if auto-print is on, with
        the configured number of copies. VAT-registered (B2B) customers
        additionally get an A4 Tax Invoice -- never instead of the receipt.

        Args:
            sale: The completed sale (items, products and payments loaded).
            is_reprint: Whether to add the DUPLICATE marking.

        Returns:
            True if the receipt was queued, False if auto-print is off.
        """
        commands = ReceiptBuilder.build_receipt(sale, is_reprint=is_reprint)
        if not PrinterService.auto_print(commands):
            return False
        PrinterService.maybe_print_b2b_invoice(sale)
        return True

    @staticmethod
    def print_receipt(sale: Sale, is_reprint: bool = False, copies: int | None = None) -> None:
        """Print a receipt the user asked for (Print / Reprint buttons).

        Ignores auto_print_receipt -- the user explicitly clicked Print.

        Args:
            sale: The sale (items, products and payments loaded).
            is_reprint: Add the DUPLICATE marking.
            copies: Number of copies; None means the configured count
                for a first print and one for a reprint.

        Raises:
            Exception: If the receipt can't be built; the caller reports it.
        """
        if copies is None:
            copies = 1 if is_reprint else PrinterService.receipt_copies()
        commands = ReceiptBuilder.build_receipt(sale, is_reprint=is_reprint)
        PrinterService.queue_commands(commands, copies)

    @staticmethod
    def maybe_print_b2b_invoice(sale: Sale) -> None:
        """Additionally print an A4 Tax Invoice if `sale` is for a VAT-registered customer.

        This is additive, not a replacement for the thermal receipt: call it
        alongside the normal receipt print, not instead of it. No-ops (with a
        log line) if no A4 printer is configured -- most shops only have a
        thermal printer, so this must never block or replace the receipt they
        do have.
        """
        if sale.customer and sale.customer.vat_number:
            PrinterService._print_a4_invoice(sale)

    @staticmethod
    def _print_a4_invoice(sale: Sale) -> None:
        """
        Generate and print A4 Tax Invoice for B2B customers.

        Args:
            sale: The sale transaction.
        """
        try:
            a4_printer = ConfigService.get("a4_printer_name")

            if not a4_printer:
                logger.warning("[PrinterService] A4 printer not configured. Skipping invoice print.")
                return

            temp_dir = tempfile.gettempdir()
            pdf_path = os.path.join(temp_dir, f"invoice_{sale.id}.pdf")

            InvoiceService.generate_pdf(sale, pdf_path)
            logger.info("[PrinterService] Generated A4 invoice: %s", pdf_path)

            PrinterService._send_pdf_to_printer(pdf_path, a4_printer)

        except Exception as e:
            logger.error("[PrinterService] Error printing A4 invoice: %s", e)

    # Only allow safe characters in printer names and file paths
    _SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.\s\\/:]+$")

    @staticmethod
    def _validate_name(value: str, label: str) -> str:
        """Validate a printer name or path contains no shell-injection characters."""
        if not PrinterService._SAFE_NAME_RE.match(value):
            raise ValueError(f"Invalid {label}: contains disallowed characters")
        return value

    @staticmethod
    def _send_pdf_to_printer(pdf_path: str, printer_name: str) -> None:
        """Send PDF file to system printer (Windows) without blocking the UI.

        Uses ``subprocess.Popen`` so the calling thread is not blocked while
        the print spooler processes the document.

        Args:
            pdf_path: Path to PDF file.
            printer_name: System printer name.
        """
        import subprocess

        try:
            PrinterService._validate_name(pdf_path, "PDF path")
            PrinterService._validate_name(printer_name, "printer name")

            subprocess.Popen(
                [
                    "powershell",
                    "-Command",
                    f'Start-Process -FilePath "{pdf_path}" -Verb Print -WindowStyle Hidden',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("[PrinterService] Sent PDF to printer: %s", printer_name)
        except ValueError as e:
            logger.error("[PrinterService] Validation error: %s", e)
        except Exception as e:
            logger.error("[PrinterService] Error sending PDF to printer: %s", e)
