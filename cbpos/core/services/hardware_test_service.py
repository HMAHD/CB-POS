"""
Hardware test service for Admin Tools.

Provides methods to test receipt printer, cash drawer,
and retrieve printer configuration.
"""

import logging
from datetime import datetime
from typing import Dict, Tuple

from cbpos.core.interfaces.iprinter import IPrinter
from cbpos.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


class HardwareTestService:
    """Test hardware connectivity and functionality."""

    @staticmethod
    def _get_printer() -> Tuple[IPrinter, str]:
        """
        Instantiate the correct printer driver based on config.

        Returns:
            Tuple of (printer instance, printer type string).
        """
        settings = ConfigService.get_all()
        p_type = settings.get("printer_type", "MOCK")

        if p_type == "MOCK":
            from cbpos.infrastructure.hardware.escpos_driver import MockPrinter

            return MockPrinter(), p_type
        else:
            from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver

            return ESCPOSDriver(), p_type

    @staticmethod
    def test_receipt_printer() -> Tuple[bool, str]:
        """
        Send a test print to the configured receipt printer.

        Returns:
            Tuple of (success: bool, message: str).
        """
        printer, p_type = HardwareTestService._get_printer()

        try:
            if not printer.connect():
                return False, "Could not connect to printer."

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commands = [
                {"type": "text", "val": "=== CB POS TEST PRINT ===", "align": "center"},
                {"type": "text", "val": ""},
                {"type": "text", "val": f"Date: {now}", "align": "center"},
                {"type": "text", "val": ""},
                {"type": "text", "val": "Printer is working!", "align": "center"},
                {"type": "feed", "lines": 3},
                {"type": "cut"},
            ]
            printer.print_commands(commands)

            if p_type == "MOCK":
                return True, "Test print sent successfully (no real hardware — using mock printer)."
            return True, "Test print sent successfully."
        except Exception as e:
            logger.error("Printer test failed: %s", e)
            return False, f"Printer test failed: {e}"
        finally:
            printer.disconnect()

    @staticmethod
    def test_cash_drawer() -> Tuple[bool, str]:
        """
        Send a kick signal to the cash drawer.

        Returns:
            Tuple of (success: bool, message: str).
        """
        printer, p_type = HardwareTestService._get_printer()

        try:
            if not printer.connect():
                return False, "Could not connect to printer (drawer uses printer connection)."

            printer.kick_drawer()

            if p_type == "MOCK":
                return True, "Drawer kick sent (no real hardware — using mock printer)."
            return True, "Cash drawer opened successfully."
        except Exception as e:
            logger.error("Cash drawer test failed: %s", e)
            return False, f"Cash drawer test failed: {e}"
        finally:
            printer.disconnect()

    @staticmethod
    def get_printer_info() -> Dict[str, str]:
        """
        Read printer configuration from settings.

        Returns:
            Dict with type, path, receipt_printer, a4_printer, paper_width.
        """
        settings = ConfigService.get_all()
        return {
            "type": settings.get("printer_type", "MOCK"),
            "path": settings.get("printer_path", "") or "(not set)",
            "receipt_printer": settings.get("receipt_printer_name", "") or "(not set)",
            "a4_printer": settings.get("a4_printer_name", "") or "(not set)",
            "paper_width": settings.get("paper_width", "80mm"),
        }
