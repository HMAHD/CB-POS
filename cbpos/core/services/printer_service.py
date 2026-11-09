import logging
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from cbpos.config import Config
from cbpos.core.models import Sale
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.shift_report_builder import ShiftReportBuilder
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

logger = logging.getLogger(__name__)

_MAX_COPIES = 5  # Settings > Hardware caps receipt copies at 5


def cleanup_print_spool(max_age_seconds: int = 86400) -> int:
    """Delete spool files older than *max_age_seconds* (default 1 day) from Config.DATA_DIR / 'print_spool'."""
    spool_dir = Config.DATA_DIR / "print_spool"
    if not spool_dir.exists():
        return 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    for path in spool_dir.glob("invoice_*.pdf"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError as e:
            logger.warning("[PrinterService] Failed to remove old spool file %s: %s", path, e)
    return removed


class PrinterService:
    """
    Single entry point for printing sale receipts.

    Every receipt print (auto after sale/refund, Receipt Options -> Print,
    reprints) builds its commands with `ReceiptBuilder` -- the same
    commands the Settings preview renders -- and queues them on the shared
    `PrintWorker` thread. VAT-registered customers additionally get an
    A4 Tax Invoice.

    Sinhala/Tamil: the builder emits labels in the receipt language as
    text commands. Printers have no Sinhala/Tamil code page, so the
    driver prints those lines as images drawn with the bundled Noto
    fonts and keeps English lines as text (see ``text_raster``).
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
    def print_shift_report(summary: dict[str, Any], x_read: bool = False) -> None:
        """Print the shift Z-Report (at close) or the mid-shift X-Read (#682).

        Queued as one job on the shared PrintWorker, like a receipt, so the
        caller hears the real outcome on job_completed / error_occurred --
        including the translated "no printer set up" message. Always one
        copy: receipt_copies is for customer receipts.

        Args:
            summary: ``ShiftService`` summary (``close_shift`` output for a Z-Report).
            x_read: True for the mid-shift X-Read.

        Raises:
            Exception: If the report can't be built; the caller reports it.
        """
        commands = ShiftReportBuilder.build_shift_report(summary, x_read=x_read)
        PrintWorker.instance().add_job("print_receipt", commands)
        logger.info(
            "[PrinterService] Queued %s for shift %s", "X-Read" if x_read else "Z-Report", summary.get("shift_id")
        )

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
    def get_spool_path(doc_number: str | None = None) -> Path:
        """Create and return a unique print spool path in Config.DATA_DIR / 'print_spool'."""
        spool_dir = Config.DATA_DIR / "print_spool"
        spool_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^\w\-.]", "_", doc_number or "doc")
        token = uuid.uuid4().hex[:8]
        return spool_dir / f"invoice_{slug}_{token}.pdf"

    @staticmethod
    def _print_a4_invoice(sale: Sale) -> None:
        """Generate and print A4 Tax Invoice for B2B customers.

        A failure (the PDF won't build, or can't be handed to the printer)
        goes out on the print worker's ``error_occurred`` -- the Sales
        screen shows it -- so the cashier knows the buyer has no tax
        invoice. No A4 printer set up is not a failure.

        Args:
            sale: The sale transaction.
        """
        a4_printer = ConfigService.get("a4_printer_name")
        if not a4_printer:
            logger.warning("[PrinterService] A4 printer not configured. Skipping invoice print.")
            return

        try:
            pdf_path = PrinterService.get_spool_path(sale.document_number)
            InvoiceService.generate_pdf(sale, str(pdf_path))
            logger.info("[PrinterService] Generated A4 invoice: %s", pdf_path)
            PrinterService._send_pdf_to_printer(str(pdf_path), a4_printer)
        except Exception as e:
            logger.exception("[PrinterService] Error printing A4 invoice for %s", sale.document_number)
            PrintWorker.instance().error_occurred.emit(
                _t("printer.a4_invoice_failed", document=sale.document_number or "", error=str(e))
            )

    @staticmethod
    def _validate_printer_name(printer_name: str | None) -> None:
        """Validate printer name: reject control characters and verify membership on Windows."""
        if not printer_name:
            return
        if any(ord(c) < 32 for c in printer_name):
            raise ValueError("Invalid printer name: contains control characters")

        if sys.platform == "win32" or "win32print" in sys.modules:
            try:
                import win32print

                if hasattr(win32print, "EnumPrinters"):
                    flags = getattr(win32print, "PRINTER_ENUM_LOCAL", 2) | getattr(
                        win32print, "PRINTER_ENUM_CONNECTIONS", 4
                    )
                    printers = win32print.EnumPrinters(flags)
                    installed = {p[2] for p in printers if len(p) > 2}
                    if printer_name not in installed:
                        raise ValueError(_t("printer.not_installed", name=printer_name))
            except ImportError:
                pass

    @staticmethod
    def _validate_pdf_path(pdf_path: str) -> None:
        """Validate PDF path contains no control characters."""
        if any(ord(c) < 32 for c in pdf_path):
            raise ValueError("Invalid PDF path: contains control characters")

    @staticmethod
    def _validate_name(value: str, label: str) -> str:
        """Legacy helper: validate a value contains no control characters."""
        if any(ord(c) < 32 for c in value):
            raise ValueError(f"Invalid {label}: contains disallowed characters")
        return value

    @staticmethod
    def _send_pdf_to_printer(pdf_path: str | Path, printer_name: str | None = None) -> None:
        """Send PDF file to system printer without building a PowerShell command string.

        On Windows: invokes win32api.ShellExecute with 'printto' (if printer_name given)
        or 'print' (Windows default printer).
        On non-Windows: invokes 'lp' via subprocess with an argv list.

        Args:
            pdf_path: Path to PDF file.
            printer_name: System printer name, or None for system default printer.

        Raises:
            ValueError: If the path or printer name has disallowed characters.
            RuntimeError: If ShellExecute fails or no PDF handler is registered.
            OSError: If the print command can't be started.
        """
        path_str = str(pdf_path)
        PrinterService._validate_pdf_path(path_str)
        if printer_name:
            PrinterService._validate_printer_name(printer_name)

        if sys.platform == "win32" or "win32api" in sys.modules:
            try:
                import win32api

                if hasattr(win32api, "ShellExecute"):
                    if printer_name:
                        ret = win32api.ShellExecute(0, "printto", path_str, f'"{printer_name}"', ".", 0)
                    else:
                        ret = win32api.ShellExecute(0, "print", path_str, None, ".", 0)
                    if isinstance(ret, int) and ret <= 32:
                        if ret == 31:  # SE_ERR_NOASSOC
                            raise RuntimeError(_t("printer.no_pdf_handler"))
                        raise RuntimeError(f"ShellExecute failed with error code {ret}")
                    logger.info("[PrinterService] Sent PDF to printer via ShellExecute: %s", printer_name or "default")
                    return
            except ImportError:
                pass
            except Exception as e:
                err_str = str(e).lower()
                winerror = getattr(e, "winerror", None)
                if winerror == 31 or "no application is associated" in err_str or "se_err_noassoc" in err_str:
                    raise RuntimeError(_t("printer.no_pdf_handler")) from e
                raise

        # Non-Windows fallback (lp)
        cmd = ["lp"]
        if printer_name:
            cmd.extend(["-d", printer_name])
        cmd.append(path_str)
        subprocess.run(cmd, check=True, timeout=60, capture_output=True)
        logger.info("[PrinterService] Sent PDF to printer via lp: %s", printer_name or "default")
