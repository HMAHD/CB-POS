import logging
import queue
import time
import uuid
from typing import Any

from escpos import printer as escpos_printer
from escpos.exceptions import DeviceNotFoundError
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from cbpos.core.constants.hardware import DEFAULT_DRAWER_PIN, DRAWER_PINS, PrinterError, PrinterType
from cbpos.core.interfaces.iprinter import IPrinter
from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.barcode import (
    calculate_barcode_width as calculate_barcode_width,
)
from cbpos.core.utils.barcode import (
    choose_barcode as choose_barcode,
)
from cbpos.core.utils.barcode import (
    code128_module_count as code128_module_count,
)
from cbpos.core.utils.barcode import (
    is_valid_ean13 as is_valid_ean13,
)
from cbpos.core.utils.thermal_image import dither_for_thermal_print
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.text_raster import needs_raster, render_text_line

logger = logging.getLogger(__name__)

_NETWORK_TIMEOUT_SECONDS = 5
_NETWORK_DEFAULT_PORT = 9100

# Job types whose data is a ReceiptBuilder-style command list. "print_commands"
# is the same job under the name the statement, label and quotation screens use.
PRINT_JOB_TYPES = frozenset({"print_receipt", "print_commands"})


def receipt_printer_configured() -> bool:
    """Return True if settings name a real receipt printer (Windows, Network or USB)."""
    return ConfigService.get_all().get("printer_type", PrinterType.NONE) in PrinterType.REAL


def printer_not_configured_message() -> str:
    """Translated message PrintWorker emits when no receipt printer is set up.

    Listeners compare against this to tell "never set up" apart from a
    real hardware failure.
    """
    return _t("printer.not_configured")


def parse_usb_id(value: str) -> tuple[int, int] | None:
    """Parse a ``VID:PID`` string such as ``0x04b8:0x0202`` or ``04b8:0202``.

    Returns:
        (vendor_id, product_id), or None if the text is not two hex numbers.
    """
    parts = (value or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        vid, pid = int(parts[0], 16), int(parts[1], 16)
    except ValueError:
        return None
    if not (0 < vid <= 0xFFFF and 0 < pid <= 0xFFFF):
        return None
    return vid, pid


def drawer_pin_setting() -> int:
    """Return the saved cash drawer kick pin (2 or 5), defaulting to 2."""
    try:
        pin = int(ConfigService.get("drawer_pin") or DEFAULT_DRAWER_PIN)
    except (TypeError, ValueError):
        return DEFAULT_DRAWER_PIN
    return pin if pin in DRAWER_PINS else DEFAULT_DRAWER_PIN


def is_connection_error(exc: BaseException) -> bool:
    """True if *exc* means the printer itself is unreachable, not a bad command.

    Covers socket/USB I/O errors (``usb.core.USBError`` is an OSError),
    escpos' DeviceNotFoundError, libusb's "not supported" (raised by pyusb
    as NotImplementedError) and pywin32's spooler errors.
    """
    if isinstance(exc, OSError | DeviceNotFoundError | NotImplementedError):
        return True
    return type(exc).__module__ == "pywintypes"


def classify_printer_error(printer_type: str, exc: BaseException) -> str:
    """Map a connection/print exception to a `PrinterError` code for the UI.

    Args:
        printer_type: The `PrinterType` that was being used.
        exc: The exception raised while opening or writing to the printer.

    Returns:
        A `PrinterError` code; FAILED when nothing more specific fits.
    """
    if printer_type == PrinterType.WIN32:
        if isinstance(exc, RuntimeError):
            return PrinterError.WIN32_UNAVAILABLE
        if isinstance(exc, DeviceNotFoundError) or type(exc).__module__ == "pywintypes":
            return PrinterError.WIN32_NOT_FOUND
        return PrinterError.FAILED
    if printer_type == PrinterType.NETWORK:
        if isinstance(exc, OSError | DeviceNotFoundError):
            return PrinterError.NETWORK_NO_ANSWER
        return PrinterError.FAILED
    if printer_type == PrinterType.USB:
        text = str(exc).lower()
        if isinstance(exc, NotImplementedError) or any(
            marker in text for marker in ("access denied", "errno 13", "busy", "not supported", "insufficient")
        ):
            return PrinterError.USB_ACCESS_DENIED
        if "not found" in text or "no such device" in text:
            return PrinterError.USB_NOT_FOUND
        return PrinterError.FAILED
    return PrinterError.NOT_CONFIGURED


class PrinterConnectionError(Exception):
    """Raised by `ESCPOSDriver.open` with a `PrinterError` code attached."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Store the error code and the underlying error text."""
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


class NullPrinter(IPrinter):
    """
    No-op printer for tests and development.

    Silently discards all commands — no console output, no side effects.
    Only used when passed to ``PrintWorker(printer=...)`` explicitly:
    with no printer configured the worker reports an error instead of
    pretending a job printed (#623).
    """

    def connect(self) -> bool:
        """No-op connect; always succeeds since there is no real device."""
        return True

    def disconnect(self) -> None:
        """No-op disconnect."""

    def print_text(self, text: str) -> None:
        """Discard the text instead of printing it."""

    def print_line(self, text: str) -> None:
        """Discard the line instead of printing it."""

    def cut(self) -> None:
        """No-op cut."""

    def print_commands(self, commands: list[dict[str, Any]]) -> None:
        """Discard the command batch instead of printing it."""

    def kick_drawer(self, pin: int | None = None) -> None:
        """No-op drawer kick."""


class ESCPOSDriver(IPrinter):
    """Real ESC/POS implementation using python-escpos.

    Reaches the printer one of three ways (``printer_type`` setting):
    WIN32 sends raw ESC/POS through the Windows spooler by printer name
    (``escpos.printer.Win32Raw``, needs pywin32), NETWORK opens a TCP
    socket to the IP, USB talks to the device directly by VID:PID.
    """

    def __init__(
        self,
        printer_type: str | None = None,
        printer_path: str | None = None,
        drawer_pin: int | None = None,
    ) -> None:
        """Create the driver with no printer connection established yet.

        Args:
            printer_type: `PrinterType` to use instead of the saved setting
                (Settings' Test buttons pass the unsaved on-screen value).
            printer_path: Printer name / IP / VID:PID to use instead of the
                saved ``printer_path``.
            drawer_pin: Drawer kick pin (2 or 5); defaults to the saved one.
        """
        self.printer = None
        self._printer_type = printer_type
        self._printer_path = printer_path
        self._drawer_pin = drawer_pin
        self.last_error: str | None = None
        self.last_error_detail = ""

    @property
    def printer_type(self) -> str:
        """The connection type this driver uses (override or saved setting)."""
        if self._printer_type is not None:
            return self._printer_type
        return ConfigService.get_all().get("printer_type", PrinterType.NONE)

    @property
    def printer_path(self) -> str:
        """The printer name / IP / VID:PID this driver uses (override or saved setting)."""
        if self._printer_path is not None:
            return self._printer_path.strip()
        return (ConfigService.get_all().get("printer_path", "") or "").strip()

    def open(self) -> None:
        """Build the python-escpos printer and open the connection.

        Opening up front (python-escpos would otherwise open lazily on the
        first write) is what lets a missing printer surface here.

        Raises:
            PrinterConnectionError: With a `PrinterError` code when the
                settings are incomplete or the printer can't be reached.
        """
        p_type, p_path = self.printer_type, self.printer_path
        self.printer = None
        try:
            if p_type == PrinterType.WIN32:
                if not p_path:
                    raise PrinterConnectionError(PrinterError.NOT_CONFIGURED)
                if not escpos_printer.Win32Raw.is_usable():
                    raise PrinterConnectionError(PrinterError.WIN32_UNAVAILABLE)
                printer = escpos_printer.Win32Raw(p_path)
            elif p_type == PrinterType.NETWORK:
                if not p_path:
                    raise PrinterConnectionError(PrinterError.NETWORK_NO_ADDRESS)
                host, _, port = p_path.partition(":")
                printer = escpos_printer.Network(
                    host,
                    port=int(port) if port.isdigit() else _NETWORK_DEFAULT_PORT,
                    timeout=_NETWORK_TIMEOUT_SECONDS,
                )
            elif p_type == PrinterType.USB:
                ids = parse_usb_id(p_path)
                if ids is None:
                    raise PrinterConnectionError(PrinterError.USB_INVALID_ID)
                printer = escpos_printer.Usb(*ids)
            else:
                raise PrinterConnectionError(PrinterError.NOT_CONFIGURED)
            printer.open()
        except PrinterConnectionError:
            raise
        except Exception as e:
            raise PrinterConnectionError(classify_printer_error(p_type, e), str(e)) from e
        self.printer = printer

    def connect(self) -> bool:
        """Connect to the configured printer.

        Returns:
            True if connected. False (without raising) otherwise; the
            reason is left in ``last_error`` (a `PrinterError` code) and
            ``last_error_detail``.
        """
        self.last_error = None
        self.last_error_detail = ""
        try:
            self.open()
            return True
        except PrinterConnectionError as e:
            self.last_error = e.code
            self.last_error_detail = e.detail
            logger.error("Printer connection failed (%s): %s", e.code, e.detail or "-")
            return False

    def disconnect(self) -> None:
        """Close the printer connection, ignoring errors if already disconnected."""
        if self.printer:
            try:
                self.printer.close()
            except Exception as e:
                logger.debug("Printer disconnect error (non-critical): %s", e)

    def print_text(self, text: str) -> None:
        """Send raw text to the printer, if connected."""
        if self.printer:
            self.printer.text(text)

    def print_line(self, text: str) -> None:
        """Send text followed by a newline, if connected."""
        if self.printer:
            self.printer.text(text + "\n")

    def cut(self) -> None:
        """Send a full paper cut command, if connected."""
        if self.printer:
            self.printer.cut()

    def print_commands(self, commands: list[dict[str, Any]]) -> None:
        """Execute a batch of print commands (text, image, barcode, feed, cut).

        Text is sent as text, except lines with Sinhala/Tamil characters,
        which no printer code page has: those are drawn as an image
        (see `text_raster`). Glyph output still needs checking on the
        shop's real printer.

        No-op if the printer is not connected. Each command is a dict with
        a "type" key; a failing command (e.g. a missing image file) is
        logged and skipped so it doesn't abort the rest of the receipt.

        Raises:
            Exception: Connection errors (see `is_connection_error`) are
                re-raised -- the printer is gone, so the job failed.
        """
        if not self.printer:
            return

        for cmd in commands:
            try:
                c_type = cmd.get("type")

                if c_type == "text":
                    val = cmd.get("val") or ""
                    if needs_raster(val):
                        # Sinhala/Tamil has no printer code page -- as text it
                        # prints "????", so draw the line as an image instead.
                        paper_width = ConfigService.get("paper_width") or "80mm"
                        self.printer.set(align="left", bold=False)
                        self.printer.image(render_text_line(cmd, paper_width))
                        continue
                    align = cmd.get("align", "left").lower()
                    bold = cmd.get("bold", False)
                    self.printer.set(align=align, bold=bold)
                    self.printer.text(val + "\n")

                elif c_type == "image":
                    path = cmd.get("path")
                    if path:
                        try:
                            img = Image.open(path)
                            paper_width = ConfigService.get("paper_width") or "80mm"
                            img = dither_for_thermal_print(img, paper_width)
                        except Exception as e:
                            logger.error("Failed to print image: %s", e)
                            continue
                        self.printer.image(img)

                elif c_type == "barcode":
                    code = cmd.get("val")
                    bc_type = cmd.get("code")
                    align = cmd.get("align", "left").lower()
                    try:
                        self.printer.set(align=align)
                    except Exception:
                        pass
                    try:
                        if bc_type == "QR":
                            # QR is 2D and needs its own ESC/POS command --
                            # printer.barcode() only knows 1D symbologies
                            # (CODE39/CODE128/EAN/etc).
                            self.printer.qr(code, center=(align == "center"))
                        else:
                            if (
                                not bc_type
                                or bc_type == "AUTO"
                                or (
                                    bc_type == "CODE128"
                                    and not (isinstance(code, str) and code.startswith(("{A", "{B", "{C")))
                                )
                            ):
                                chosen_type, payload = choose_barcode(code)
                            else:
                                chosen_type, payload = bc_type, code
                            kwargs: dict[str, Any] = {"function_type": "B"}
                            if "width" in cmd:
                                kwargs["width"] = cmd["width"]
                            if "height" in cmd:
                                kwargs["height"] = cmd["height"]
                            self.printer.barcode(payload, chosen_type, **kwargs)
                    except Exception as e:
                        if is_connection_error(e):
                            raise
                        logger.error("Failed to print barcode %r: %s", code, e)
                        raise RuntimeError(_t("printer.barcode_failed", code=str(code or ""))) from e

                elif c_type == "feed":
                    lines = cmd.get("lines", 1)
                    self.printer.text("\n" * lines)

                elif c_type == "cut":
                    partial = cmd.get("partial", True)
                    if partial:
                        self.printer.cut(mode="PART")
                    else:
                        self.printer.cut(mode="FULL")

            except Exception as e:
                # A lost printer or barcode failure must fail the job, not print "nothing" as success.
                if is_connection_error(e) or isinstance(e, RuntimeError):
                    raise
                logger.error("Error processing print command %s: %s", cmd.get("type"), e)

    def kick_drawer(self, pin: int | None = None) -> None:
        """Pulse the cash drawer kick pin (2 or 5), if connected.

        Args:
            pin: Kick pin; falls back to the driver's pin, then the saved
                ``drawer_pin`` setting.
        """
        if self.printer:
            pin = pin or self._drawer_pin or drawer_pin_setting()
            self.printer.cashdraw(pin if pin in DRAWER_PINS else DEFAULT_DRAWER_PIN)


class PrintWorker(QThread):
    """Background thread for asynchronous print job processing.

    Resolves the printer once per run cycle from application settings:

    - printer_type == "WIN32" / "NETWORK" / "USB" → ESCPOSDriver (real hardware)
    - anything else → no printer: the job is skipped and error_occurred
      carries ``printer_not_configured_message()``. Never job_completed --
      screens show "sent to printer" on that signal (#623).
      Exception: kick_drawer jobs are dropped silently (no printer, no
      drawer), so every cash sale doesn't raise a "not set up" error.

    If the real printer fails to connect, the job is skipped and the failure
    is logged and reported via error_occurred.
    """

    error_occurred = pyqtSignal(str)  # Emitted when a print job fails
    job_completed = pyqtSignal()  # Emitted when a print job succeeds
    job_result = pyqtSignal(str, bool, str)  # (job_id, ok, message)

    _instance: "PrintWorker | None" = None

    def __init__(self, printer: IPrinter | None = None) -> None:
        """Create the worker with an optional fixed printer and an empty job queue.

        Args:
            printer: Printer to use for every job, bypassing settings-based
                resolution. If None, ``_resolve_printer`` picks one from
                settings on each run.
        """
        super().__init__()
        self.printer = printer
        self._queue: queue.Queue[tuple[str, str, Any]] = queue.Queue()
        self.running = True

    @classmethod
    def instance(cls) -> "PrintWorker":
        """Return the one shared PrintWorker for the app's lifetime.

        Every caller must go through this instead of `PrintWorker()`. run()
        below loops until stop() is called (by design -- add_job() keeps
        reusing the same running thread for jobs queued later), so a
        locally-scoped `PrintWorker()` is still running when its only
        Python reference goes out of scope at the end of the calling
        function; Qt then aborts the whole process ("QThread: Destroyed
        while thread is still running") rather than merely raising a
        catchable exception. A single persistent instance, kept alive on
        the class itself, avoids that entirely.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def shutdown(cls) -> None:
        """Stop and join the shared worker on app exit, if one was created."""
        if cls._instance is not None:
            cls._instance.stop()
            cls._instance.wait(5000)
            cls._instance = None

    def add_job(self, job_type: str, data: Any = None) -> str:
        """Queue a print job. Starts the thread if not already running.

        Args:
            job_type: One of `PRINT_JOB_TYPES` ('print_receipt' /
                'print_commands', both a builder command list) or
                'kick_drawer'. Any other type is reported via
                error_occurred and job_result when it is processed -- never
                as completed.
            data: Command list for print jobs; for kick_drawer, optionally
                  a list of payment method strings (e.g. ['CASH']) to allow
                  drawer_on_cash_only filtering.

        Returns:
            Unique 32-character hex job identifier (UUID4 hex).
        """
        job_id = uuid.uuid4().hex
        self._queue.put((job_id, job_type, data))
        if not self.isRunning():
            self.start()
        return job_id

    def stop(self) -> None:
        """Signal the worker to stop after current job completes."""
        self.running = False

    @staticmethod
    def _drawer_wanted(data: Any) -> bool:
        """Honour ``drawer_on_cash_only``: kick only if manual or a CASH payment is in *data*."""
        if isinstance(data, dict):
            if data.get("manual", False):
                return True
            method_kinds = [str(k).upper() for k in data.get("method_kinds", [])]
        elif isinstance(data, (list, tuple, set)):
            from cbpos.core.services.payment_service import classify_method_name

            method_kinds = [classify_method_name(str(m)).upper() for m in data]
        else:
            method_kinds = []

        if not ConfigService.get("drawer_on_cash_only"):
            return True

        if "CASH" in method_kinds:
            return True

        if not method_kinds:
            logger.info("Drawer skipped — no payment methods provided (drawer_on_cash_only=True)")
        else:
            logger.info("Drawer skipped — no cash payment (drawer_on_cash_only=True)")
        return False

    def run(self) -> None:
        """Process queued jobs until stopped.

        Every job ends in exactly one of: job_completed (it really went to
        the printer), error_occurred, or -- only for a drawer kick that
        isn't wanted or has no printer -- silence. An unknown job type or
        a print job whose data isn't a command list is an error, so no
        screen ever reports "sent to printer" for something that printed
        nothing (#625).

        Resolves the printer fresh per job (so a mid-session settings
        change takes effect), connects, runs the job, then always
        disconnects. A job whose printer fails to connect is skipped and
        logged rather than retried.
        """
        while self.running:
            try:
                item = self._queue.get(timeout=1)
            except queue.Empty:
                if not self.running:
                    break
                continue

            if len(item) == 3:
                job_id, job_type, data = item
            else:
                job_id = uuid.uuid4().hex
                job_type, data = item

            if job_type == "a4_invoice":
                try:
                    from cbpos.core.services.printer_service import PrinterService

                    PrinterService.process_a4_invoice_job(data)
                    self.job_completed.emit()
                    self.job_result.emit(job_id, True, "")
                except Exception as e:
                    logger.error("A4 invoice print job failed for %r: %s", data, e)
                    doc = getattr(e, "document_number", str(data))
                    err_msg = _t("printer.a4_invoice_failed", document=doc, error=str(e))
                    self.error_occurred.emit(err_msg)
                    self.job_result.emit(job_id, False, err_msg)
                continue

            is_print = job_type in PRINT_JOB_TYPES
            if not is_print and job_type != "kick_drawer":
                logger.error("Unknown print job type %r — nothing printed.", job_type)
                err_msg = _t("printer.job_unsupported")
                self.error_occurred.emit(err_msg)
                self.job_result.emit(job_id, False, err_msg)
                continue
            if is_print and not isinstance(data, list):
                logger.error("Print job %r has no command list (%s) — nothing printed.", job_type, type(data).__name__)
                err_msg = _t("printer.job_unsupported")
                self.error_occurred.emit(err_msg)
                self.job_result.emit(job_id, False, err_msg)
                continue

            current_printer = self._resolve_printer()
            if current_printer is None:
                if job_type == "kick_drawer":
                    # The drawer is wired through the receipt printer: no
                    # printer, no drawer. Stay silent -- every cash sale
                    # queues one, and nothing waits on it.
                    logger.debug("No receipt printer configured — skipping drawer kick.")
                    self.job_result.emit(job_id, False, "drawer_skipped:no_printer")
                    continue
                logger.warning("No receipt printer configured — skipping %s job.", job_type)
                err_msg = printer_not_configured_message()
                self.error_occurred.emit(err_msg)
                self.job_result.emit(job_id, False, err_msg)
                continue

            if job_type == "kick_drawer" and not self._drawer_wanted(data):
                self.job_result.emit(job_id, False, "drawer_skipped:not_cash")
                continue

            try:
                if not current_printer.connect():
                    msg = "Printer not available — skipping %s job. Check printer settings in Settings > Hardware."
                    logger.warning(msg, job_type)
                    err_msg = _t("printer.not_available")
                    self.error_occurred.emit(err_msg)
                    self.job_result.emit(job_id, False, err_msg)
                    continue

                if job_type == "kick_drawer":
                    current_printer.kick_drawer()
                else:
                    current_printer.print_commands(data)

                current_printer.disconnect()
                self.job_completed.emit()
                self.job_result.emit(job_id, True, "")

            except Exception as e:
                logger.error("Print job '%s' failed: %s", job_type, e)
                current_printer.disconnect()
                err_msg = str(e)
                self.error_occurred.emit(err_msg)
                self.job_result.emit(job_id, False, err_msg)

            time.sleep(0.1)

    def _resolve_printer(self) -> IPrinter | None:
        """Pick the printer for the next job: the injected one, the real
        driver if settings name one, else None (no printer configured)."""
        if self.printer:
            return self.printer

        if receipt_printer_configured():
            return ESCPOSDriver()

        return None
