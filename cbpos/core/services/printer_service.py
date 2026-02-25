import logging
import os
import re
import tempfile
from cbpos.core.models import Sale
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)


class PrinterService:
    """
    Service for intelligent print routing based on customer type.
    Routes to thermal receipt printer (B2C) or A4 invoice printer (B2B).
    """

    @staticmethod
    def print_transaction(sale: Sale) -> None:
        """
        Route transaction to appropriate printer based on customer type.

        Logic:
        - B2B (VAT Registered): Generate PDF → Print to A4 printer
        - B2C (Walk-in): Format ESC/POS → Print to thermal printer

        Args:
            sale (Sale): The completed sale transaction
        """
        # Check if customer has VAT number (B2B)
        is_b2b = sale.customer and sale.customer.vat_number

        if is_b2b:
            PrinterService._print_a4_invoice(sale)
        else:
            PrinterService._print_thermal_receipt(sale)

    @staticmethod
    def _print_a4_invoice(sale: Sale) -> None:
        """
        Generate and print A4 Tax Invoice for B2B customers.

        Args:
            sale (Sale): The sale transaction
        """
        try:
            # Get A4 printer name from config
            a4_printer = ConfigService.get("a4_printer_name")

            if not a4_printer:
                logger.warning("[PrinterService] A4 printer not configured. Skipping invoice print.")
                return

            # Generate PDF in temp directory
            temp_dir = tempfile.gettempdir()
            pdf_path = os.path.join(temp_dir, "invoice_{0}.pdf".format(sale.id))

            # Generate PDF
            InvoiceService.generate_pdf(sale, pdf_path)
            logger.info("[PrinterService] Generated A4 invoice: {0}".format(pdf_path))

            # Print PDF (platform-specific)
            PrinterService._send_pdf_to_printer(pdf_path, a4_printer)

        except Exception as e:
            logger.error("[PrinterService] Error printing A4 invoice: {0}".format(e))

    @staticmethod
    def _print_thermal_receipt(sale: Sale) -> None:
        """
        Format and print thermal receipt for B2C customers.

        Args:
            sale (Sale): The sale transaction
        """
        try:
            # Check if auto-print is enabled
            if not ConfigService.get("auto_print_receipt"):
                return

            # Get receipt printer name
            receipt_printer = ConfigService.get("receipt_printer_name")
            if not receipt_printer:
                logger.warning("[PrinterService] Receipt printer not configured. Skipping print.")
                return

            # Get number of copies
            copies = ConfigService.get("receipt_copies") or 1

            # Format receipt (ESC/POS)
            receipt_data = PrinterService._format_receipt(sale)

            # Print copies
            for i in range(copies):
                PrinterService._send_to_thermal_printer(receipt_data, receipt_printer)
                logger.warning("[PrinterService] Printed receipt copy {0}/{1}".format(i + 1, copies))

        except Exception as e:
            logger.error("[PrinterService] Error printing thermal receipt: {0}".format(e))

    @staticmethod
    def _format_receipt(sale: Sale) -> bytes:
        """
        Format sale as ESC/POS receipt data.

        Args:
            sale (Sale): The sale transaction

        Returns:
            bytes: ESC/POS formatted receipt data
        """
        # ESC/POS Commands
        ESC = b"\x1b"
        INIT = ESC + b"@"  # Initialize printer
        CENTER = ESC + b"a\x01"  # Center alignment
        LEFT = ESC + b"a\x00"  # Left alignment
        BOLD_ON = ESC + b"E\x01"  # Bold on
        BOLD_OFF = ESC + b"E\x00"  # Bold off
        CUT = ESC + b"i"  # Cut paper

        receipt = INIT

        # Header
        receipt += CENTER
        receipt += BOLD_ON
        header = ConfigService.get("receipt_header") or "Ceylon Byte POS"
        receipt += header.encode("utf-8") + b"\n"
        receipt += BOLD_OFF

        shop_name = ConfigService.get("shop_name") or ""
        shop_address = ConfigService.get("shop_address") or ""
        shop_phone = ConfigService.get("shop_phone") or ""

        receipt += shop_name.encode("utf-8") + b"\n"
        receipt += shop_address.encode("utf-8") + b"\n"
        receipt += shop_phone.encode("utf-8") + b"\n"
        receipt += b"=" * 42 + b"\n"

        # Sale Info
        receipt += LEFT
        receipt += "Date: {0}\n".format(sale.date.strftime("%Y-%m-%d %H:%M")).encode("utf-8")
        receipt += "Invoice: INV-{0:06d}\n".format(sale.id).encode("utf-8")
        if sale.customer:
            receipt += "Customer: {0}\n".format(sale.customer.name).encode("utf-8")
        receipt += b"-" * 42 + b"\n"

        # Items
        for item in sale.items:
            product_name = item.product.name if item.product else "Unknown"
            qty = "{0:.3f}".format(item.quantity) if item.quantity % 1 != 0 else "{0}".format(int(item.quantity))
            price = item.unit_price * item.quantity - item.discount
            receipt += "{0:<25}\n".format(product_name[:25]).encode("utf-8")
            receipt += "  {0} x Rs.{1:,.2f}".format(qty, item.unit_price).encode("utf-8")
            receipt += "{0:>12,.2f}\n".format(price).encode("utf-8")

        receipt += b"-" * 42 + b"\n"

        # Totals
        receipt += BOLD_ON
        receipt += "{0:<30}Rs.{1:>10,.2f}\n".format("TOTAL:", sale.total_amount).encode("utf-8")
        receipt += BOLD_OFF

        if sale.payment_method:
            receipt += "Payment: {0}\n".format(sale.payment_method).encode("utf-8")

        # Footer
        receipt += b"=" * 42 + b"\n"
        receipt += CENTER
        footer = ConfigService.get("receipt_footer") or "Thank You!"
        receipt += footer.encode("utf-8") + b"\n\n"

        # Cut paper
        receipt += CUT

        return receipt

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
        """
        Send PDF file to system printer (Windows).

        Args:
            pdf_path (str): Path to PDF file
            printer_name (str): System printer name
        """
        import subprocess

        try:
            PrinterService._validate_name(pdf_path, "PDF path")
            PrinterService._validate_name(printer_name, "printer name")

            # Windows: Use SumatraPDF or Adobe Reader for silent printing
            # For now, use default print command
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    'Start-Process -FilePath "{0}" -Verb Print -WindowStyle Hidden'.format(pdf_path),
                ],
                check=True,
            )
            logger.info("[PrinterService] Sent PDF to printer: %s", printer_name)
        except ValueError as e:
            logger.error("[PrinterService] Validation error: %s", e)
        except Exception as e:
            logger.error("[PrinterService] Error sending PDF to printer: %s", e)

    @staticmethod
    def _send_to_thermal_printer(data: bytes, printer_name: str) -> None:
        """
        Send ESC/POS data to thermal printer.

        Args:
            data (bytes): ESC/POS formatted data
            printer_name (str): System printer name
        """
        try:
            # For Windows, write directly to printer port
            # This is a simplified implementation
            # In production, use python-escpos or win32print
            import subprocess

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".prn")
            temp_file.write(data)
            temp_file.close()

            PrinterService._validate_name(printer_name, "printer name")

            # Send to printer using copy command
            subprocess.run(
                [
                    "cmd",
                    "/c",
                    'copy /b "{0}" "{1}"'.format(temp_file.name, printer_name),
                ],
                check=True,
                capture_output=True,
            )

            os.unlink(temp_file.name)
            logger.info("[PrinterService] Sent receipt to thermal printer: {0}".format(printer_name))

        except Exception as e:
            logger.error("[PrinterService] Error sending to thermal printer: {0}".format(e))
