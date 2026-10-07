"""
Constants for the receipt printer connection and hardware test results.

Settings store ``printer_type`` (one of `PrinterType`) plus ``printer_path``,
whose meaning depends on the type: the Windows printer name (WIN32), the
IP address (NETWORK) or ``VID:PID`` (USB).
"""


class PrinterType:
    """How CB POS reaches the receipt printer."""

    NONE = "NONE"
    WIN32 = "WIN32"  # Windows printer by name, raw ESC/POS through the spooler
    NETWORK = "NETWORK"  # Raw TCP to an IP address (port 9100)
    USB = "USB"  # Direct USB by VID:PID (needs a WinUSB driver on Windows)

    REAL = (WIN32, NETWORK, USB)


DEFAULT_DRAWER_PIN = 2
DRAWER_PINS = (2, 5)


class PrinterError:
    """Why a printer could not be reached. The UI turns these into translated text."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    WIN32_NOT_FOUND = "WIN32_NOT_FOUND"
    WIN32_UNAVAILABLE = "WIN32_UNAVAILABLE"
    NETWORK_NO_ADDRESS = "NETWORK_NO_ADDRESS"
    NETWORK_NO_ANSWER = "NETWORK_NO_ANSWER"
    USB_INVALID_ID = "USB_INVALID_ID"
    USB_NOT_FOUND = "USB_NOT_FOUND"
    USB_ACCESS_DENIED = "USB_ACCESS_DENIED"
    FAILED = "FAILED"


class HardwareTestOutcome:
    """Success codes for a hardware test."""

    PRINT_SENT = "PRINT_SENT"
    PRINT_SENT_WIN32 = "PRINT_SENT_WIN32"
    DRAWER_SENT = "DRAWER_SENT"
    DRAWER_SENT_WIN32 = "DRAWER_SENT_WIN32"
