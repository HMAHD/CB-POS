import logging
import os
import re
import tempfile
from cbpos.core.models import Sale
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

logger = logging.getLogger(__name__)


class PrinterService:
    """
    Service for intelligent print routing based on customer type.
    Routes to thermal receipt printer (B2C) or A4 invoice printer (B2B).
    """

    @staticmethod
    def print_transaction(sale: Sale, is_reprint: bool = False) -> None:
        """
        Route transaction to appropriate printer based on customer type.

        Logic:
        - B2B (VAT Registered): Generate PDF -> Print to A4 printer
        - B2C (Walk-in): Build receipt commands -> Print via PrintWorker

        Args:
            sale: The completed sale transaction.
            is_reprint: Whether this is a reprint (adds DUPLICATE marking).
        """
        is_b2b = sale.customer and sale.customer.vat_number

        if is_b2b:
            PrinterService._print_a4_invoice(sale)
        else:
            PrinterService._print_thermal_receipt(sale, is_reprint=is_reprint)

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
            pdf_path = os.path.join(temp_dir, "invoice_{0}.pdf".format(sale.id))

            InvoiceService.generate_pdf(sale, pdf_path)
            logger.info("[PrinterService] Generated A4 invoice: %s", pdf_path)

            PrinterService._send_pdf_to_printer(pdf_path, a4_printer)

        except Exception as e:
            logger.error("[PrinterService] Error printing A4 invoice: %s", e)

    @staticmethod
    def _print_thermal_receipt(sale: Sale, is_reprint: bool = False) -> None:
        """
        Build receipt commands via ReceiptBuilder and print via PrintWorker.

        Args:
            sale: The sale transaction.
            is_reprint: Whether this is a reprint.
        """
        try:
            if not ConfigService.get("auto_print_receipt"):
                return

            copies = ConfigService.get("receipt_copies") or 1
            commands = ReceiptBuilder.build_receipt(sale, is_reprint=is_reprint)

            worker = PrintWorker.instance()
            for i in range(copies):
                worker.add_job("print_receipt", commands)
                logger.info("[PrinterService] Queued receipt copy %d/%d", i + 1, copies)

        except Exception as e:
            logger.error("[PrinterService] Error printing thermal receipt: %s", e)

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
                    'Start-Process -FilePath "{0}" -Verb Print -WindowStyle Hidden'.format(pdf_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("[PrinterService] Sent PDF to printer: %s", printer_name)
        except ValueError as e:
            logger.error("[PrinterService] Validation error: %s", e)
        except Exception as e:
            logger.error("[PrinterService] Error sending PDF to printer: %s", e)
