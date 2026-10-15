"""Turn hardware test results into translated, styled feedback (#624).

The service only returns codes; the wording lives here so it follows the
current UI language. Shared by Settings -> Hardware and Admin Tools.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from cbpos.core.constants.hardware import HardwareTestOutcome, PrinterError
from cbpos.core.services.hardware_test_service import HardwareTestResult
from cbpos.i18n import _t
from cbpos.ui.utils.style_helpers import set_status_class

_KEYS = {
    HardwareTestOutcome.PRINT_SENT: "printer.test.print_sent",
    HardwareTestOutcome.PRINT_SENT_WIN32: "printer.test.print_sent_win32",
    HardwareTestOutcome.DRAWER_SENT: "printer.test.drawer_sent",
    HardwareTestOutcome.DRAWER_SENT_WIN32: "printer.test.drawer_sent_win32",
    PrinterError.NOT_CONFIGURED: "printer.test.not_configured",
    PrinterError.WIN32_NOT_FOUND: "printer.test.win32_not_found",
    PrinterError.WIN32_UNAVAILABLE: "printer.test.win32_unavailable",
    PrinterError.NETWORK_NO_ADDRESS: "printer.test.network_no_address",
    PrinterError.NETWORK_NO_ANSWER: "printer.test.network_no_answer",
    PrinterError.USB_INVALID_ID: "printer.test.usb_invalid_id",
    PrinterError.USB_NOT_FOUND: "printer.test.usb_not_found",
    PrinterError.USB_ACCESS_DENIED: "printer.test.usb_access_denied",
    PrinterError.FAILED: "printer.test.failed",
}


def hardware_test_message(result: HardwareTestResult) -> str:
    """Translated sentence for a hardware test result.

    Args:
        result: What `HardwareTestService` returned.

    Returns:
        The message in the current UI language; unknown codes read as a
        generic failure.
    """
    key = _KEYS.get(result.code, "printer.test.failed")
    path = result.printer_path
    return _t(key, name=path, ip=path, usb_id=path)


def show_hardware_test_result(label: QLabel, result: HardwareTestResult) -> None:
    """Show a test result in *label*: translated text, success/warning style, error detail as tooltip.

    Args:
        label: The result label next to the test buttons.
        result: What `HardwareTestService` returned.
    """
    set_hardware_test_status(label, hardware_test_message(result), "success-hint" if result.success else "warning-hint")
    label.setToolTip(result.detail)


def set_hardware_test_status(label: QLabel, text: str, css_class: str) -> None:
    """Put *text* in *label* with a QSS class, vertically centred next to the buttons.

    Args:
        label: The result label next to the test buttons.
        text: Already-translated text.
        css_class: ``success-hint``, ``warning-hint`` or ``muted`` (in progress).
    """
    label.setToolTip("")
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    set_status_class(label, css_class, text)
