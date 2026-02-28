"""
Hardware test service for Admin Tools.

Provides methods to test receipt printer, cash drawer,
and retrieve printer configuration.
"""

import logging
from datetime import datetime
from typing import Dict, Tuple

from cbpos.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


class HardwareTestService:
    """Test hardware connectivity and functionality."""

    @staticmethod
    def test_receipt_printer() -> Tuple[bool, str]:
        """
        Send a test print to the configured receipt printer.

        Returns:
            Tuple of (success: bool, message: str).
        """
        settings = ConfigService.get_all()
        p_type = settings.get("printer_type", "MOCK")

        if p_type == "MOCK":
            from cbpos.infrastructure.hardware.escpos_driver import MockPrinter

            printer = MockPrinter()
        else:
            from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver

            printer = ESCPOSDriver()

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
            printer.disconnect()

            if p_type == "MOCK":
                return True, "Test print sent successfully (no real hardware — using mock printer)."
            return True, "Test print sent successfully."
        except Exception as e:
            logger.error("Printer test failed: %s", e)
            return False, f"Printer test failed: {e}"

    @staticmethod
    def test_cash_drawer() -> Tuple[bool, str]:
        """
        Send a kick signal to the cash drawer.

        Returns:
            Tuple of (success: bool, message: str).
        """
        settings = ConfigService.get_all()
        p_type = settings.get("printer_type", "MOCK")

        if p_type == "MOCK":
            from cbpos.infrastructure.hardware.escpos_driver import MockPrinter

            printer = MockPrinter()
        else:
            from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver

            printer = ESCPOSDriver()

        try:
            if not printer.connect():
                return False, "Could not connect to printer (drawer uses printer connection)."

            printer.kick_drawer()
            printer.disconnect()

            if p_type == "MOCK":
                return True, "Drawer kick sent (no real hardware — using mock printer)."
            return True, "Cash drawer opened successfully."
        except Exception as e:
            logger.error("Cash drawer test failed: %s", e)
            return False, f"Cash drawer test failed: {e}"

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
