"""
Hardware test service for Settings -> Hardware and Admin Tools.

Sends a test slip / drawer kick to the receipt printer and reports the
outcome as a code (`HardwareTestOutcome` or `PrinterError`) that the UI
translates. Tests can target values that are on screen but not saved yet.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from cbpos.core.constants.hardware import HardwareTestOutcome, PrinterError, PrinterType
from cbpos.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HardwareTestResult:
    """Outcome of a hardware test.

    Attributes:
        success: True if the job reached the printer (or Windows spooler).
        code: A `HardwareTestOutcome` on success, else a `PrinterError`.
        printer_type: The `PrinterType` that was tested.
        printer_path: The printer name / IP / VID:PID that was tested.
        detail: The underlying error text (for logs / tooltips), if any.
    """

    success: bool
    code: str
    printer_type: str = PrinterType.NONE
    printer_path: str = ""
    detail: str = ""


class HardwareTestService:
    """Test hardware connectivity and functionality."""

    @staticmethod
    def _target(printer_type: str | None, printer_path: str | None) -> tuple[str, str]:
        """Resolve which printer to test: explicit values win over saved settings.

        Args:
            printer_type: Unsaved on-screen `PrinterType`, or None for the saved one.
            printer_path: Unsaved on-screen name / IP / VID:PID, or None for the saved one.

        Returns:
            (printer_type, printer_path).
        """
        settings = ConfigService.get_all()
        if printer_type is None:
            printer_type = settings.get("printer_type", PrinterType.NONE)
        if printer_path is None:
            printer_path = settings.get("printer_path", "") or ""
        return printer_type or PrinterType.NONE, printer_path.strip()

    @staticmethod
    def _run(
        printer_type: str | None,
        printer_path: str | None,
        job: str,
        pin: int | None = None,
    ) -> HardwareTestResult:
        """Connect, run one test job ("print" or "drawer"), disconnect.

        Args:
            printer_type: `PrinterType` override, or None for the saved setting.
            printer_path: Printer value override, or None for the saved setting.
            job: "print" for a test slip, "drawer" for a drawer kick.
            pin: Drawer kick pin for the "drawer" job.

        Returns:
            The test outcome; never raises.
        """
        from cbpos.infrastructure.hardware.escpos_driver import (
            ESCPOSDriver,
            PrinterConnectionError,
            classify_printer_error,
        )

        p_type, p_path = HardwareTestService._target(printer_type, printer_path)
        if p_type not in PrinterType.REAL:
            return HardwareTestResult(False, PrinterError.NOT_CONFIGURED, p_type, p_path)

        driver = ESCPOSDriver(printer_type=p_type, printer_path=p_path, drawer_pin=pin)
        try:
            driver.open()
            if job == "drawer":
                driver.kick_drawer(pin)
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                driver.print_commands(
                    [
                        {"type": "text", "val": "=== CB POS TEST PRINT ===", "align": "center"},
                        {"type": "text", "val": ""},
                        {"type": "text", "val": f"Date: {now}", "align": "center"},
                        {"type": "text", "val": ""},
                        {"type": "text", "val": "Printer is working!", "align": "center"},
                        {"type": "feed", "lines": 3},
                        {"type": "cut"},
                    ]
                )
        except PrinterConnectionError as e:
            logger.error("Hardware test (%s) could not reach printer (%s): %s", job, e.code, e.detail or "-")
            return HardwareTestResult(False, e.code, p_type, p_path, e.detail)
        except Exception as e:
            logger.error("Hardware test (%s) failed: %s", job, e)
            return HardwareTestResult(False, classify_printer_error(p_type, e), p_type, p_path, str(e))
        finally:
            driver.disconnect()

        win32 = p_type == PrinterType.WIN32
        if job == "drawer":
            code = HardwareTestOutcome.DRAWER_SENT_WIN32 if win32 else HardwareTestOutcome.DRAWER_SENT
        else:
            code = HardwareTestOutcome.PRINT_SENT_WIN32 if win32 else HardwareTestOutcome.PRINT_SENT
        return HardwareTestResult(True, code, p_type, p_path)

    @staticmethod
    def test_receipt_printer(printer_type: str | None = None, printer_path: str | None = None) -> HardwareTestResult:
        """Send a test slip to the receipt printer.

        Args:
            printer_type: `PrinterType` to test instead of the saved one
                (Settings passes the unsaved on-screen choice).
            printer_path: Printer name / IP / VID:PID to test instead of the saved one.

        Returns:
            The test outcome, with a code the UI turns into translated text.
        """
        return HardwareTestService._run(printer_type, printer_path, "print")

    @staticmethod
    def test_cash_drawer(
        printer_type: str | None = None,
        printer_path: str | None = None,
        pin: int | None = None,
    ) -> HardwareTestResult:
        """Send a kick signal to the cash drawer through the receipt printer.

        Args:
            printer_type: `PrinterType` to test instead of the saved one.
            printer_path: Printer name / IP / VID:PID to test instead of the saved one.
            pin: Drawer kick pin (2 or 5); None uses the saved ``drawer_pin``.

        Returns:
            The test outcome, with a code the UI turns into translated text.
        """
        return HardwareTestService._run(printer_type, printer_path, "drawer", pin)

    @staticmethod
    def get_printer_info() -> dict[str, str]:
        """Read printer configuration from settings.

        Returns:
            Dict with type, path, receipt_printer, a4_printer, paper_width.
            Unset values are empty strings.
        """
        settings = ConfigService.get_all()
        return {
            "type": settings.get("printer_type", PrinterType.NONE),
            "path": settings.get("printer_path", "") or "",
            "receipt_printer": settings.get("receipt_printer_name", "") or "",
            "a4_printer": settings.get("a4_printer_name", "") or "",
            "paper_width": settings.get("paper_width", "80mm"),
        }
