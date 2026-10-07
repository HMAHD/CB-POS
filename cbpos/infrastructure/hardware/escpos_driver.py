import logging
import queue
import time
from typing import Any

from escpos.printer import Network, Usb
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from cbpos.core.interfaces.iprinter import IPrinter
from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.thermal_image import dither_for_thermal_print
from cbpos.i18n import _t

logger = logging.getLogger(__name__)

_REAL_PRINTER_TYPES = ("USB", "NETWORK")


def receipt_printer_configured() -> bool:
    """Return True if settings name a real receipt printer (USB or Network)."""
    return ConfigService.get_all().get("printer_type", "NONE") in _REAL_PRINTER_TYPES


def printer_not_configured_message() -> str:
    """Translated message PrintWorker emits when no receipt printer is set up.

    Listeners compare against this to tell "never set up" apart from a
    real hardware failure.
    """
    return _t("printer.not_configured")


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

    def kick_drawer(self) -> None:
        """No-op drawer kick."""


class ESCPOSDriver(IPrinter):
    """Real ESC/POS implementation using python-escpos for USB and Network printers."""

    def __init__(self) -> None:
        """Create the driver with no printer connection established yet."""
        self.printer = None

    def connect(self) -> bool:
        """Connect to the USB or Network printer configured in settings.

        Returns:
            True if connected. False (without raising) if the configured
            printer type is unrecognized, required settings are missing
            (VID:PID for USB, IP address for Network), or the underlying
            connection attempt raises an exception.
        """
        settings = ConfigService.get_all()
        p_type = settings.get("printer_type", "NONE")
        p_path = settings.get("printer_path", "")

        try:
            if p_type == "USB":
                if p_path and ":" in p_path:
                    vid, pid = p_path.split(":")
                    self.printer = Usb(int(vid, 16), int(pid, 16))
                else:
                    logger.warning(
                        "USB printer requires VID:PID in settings (e.g. 0x04b8:0x0202). "
                        "Configure in Settings > Hardware."
                    )
                    return False
            elif p_type == "NETWORK":
                if p_path:
                    self.printer = Network(p_path)
                else:
                    logger.warning("Network printer requires an IP address. Configure in Settings > Hardware.")
                    return False
            else:
                return False

            return True
        except Exception as e:
            logger.error("Printer connection failed: %s", e)
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

        No-op if the printer is not connected. Each command is a dict with
        a "type" key; a failing command (e.g. a missing image file) is
        logged and skipped so it doesn't abort the rest of the receipt.
        """
        if not self.printer:
            return

        for cmd in commands:
            try:
                c_type = cmd.get("type")

                if c_type == "text":
                    align = cmd.get("align", "left").upper()
                    bold = cmd.get("bold", False)
                    self.printer.set(align=align, bold=bold)
                    self.printer.text(cmd.get("val") + "\n")

                elif c_type == "image":
                    path = cmd.get("path")
                    if path:
                        try:
                            img = Image.open(path)
                            paper_width = ConfigService.get("paper_width") or "80mm"
                            img = dither_for_thermal_print(img, paper_width)
                            self.printer.image(img)
                        except Exception as e:
                            logger.error("Failed to print image: %s", e)

                elif c_type == "barcode":
                    code = cmd.get("val")
                    bc_type = cmd.get("code", "CODE39")
                    try:
                        if bc_type == "QR":
                            # QR is 2D and needs its own ESC/POS command --
                            # printer.barcode() only knows 1D symbologies
                            # (CODE39/CODE128/EAN/etc).
                            self.printer.qr(code, center=(cmd.get("align", "left") == "center"))
                        else:
                            self.printer.barcode(code, bc_type, function_type="B")
                    except Exception as e:
                        logger.error("Failed to print barcode: %s", e)

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
                logger.error("Error processing print command %s: %s", cmd.get("type"), e)

    def kick_drawer(self) -> None:
        """Pulse the cash drawer kick pin, if connected."""
        if self.printer:
            self.printer.cashdraw(2)


class PrintWorker(QThread):
    """Background thread for asynchronous print job processing.

    Resolves the printer once per run cycle from application settings:
    - printer_type == "USB" / "NETWORK" → ESCPOSDriver (real hardware)
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
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
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

    def add_job(self, job_type: str, data: Any = None) -> None:
        """Queue a print job. Starts the thread if not already running.

        Args:
            job_type: 'print_receipt' or 'kick_drawer'
            data: Command list for print_receipt; for kick_drawer, optionally
                  a list of payment method strings (e.g. ['CASH']) to allow
                  drawer_on_cash_only filtering.
        """
        self._queue.put((job_type, data))
        if not self.isRunning():
            self.start()

    def stop(self) -> None:
        """Signal the worker to stop after current job completes."""
        self.running = False

    def run(self) -> None:
        """Process queued jobs until stopped.

        Resolves the printer fresh per job (so a mid-session settings
        change takes effect), connects, runs the job, then disconnects.
        A job whose printer fails to connect is skipped and logged rather
        than retried. For "kick_drawer" jobs, honors the
        ``drawer_on_cash_only`` setting by skipping the drawer pulse
        unless a cash payment method was included in the job data.
        """
        while self.running:
            try:
                job_type, data = self._queue.get(timeout=1)
            except queue.Empty:
                if not self.running:
                    break
                continue

            current_printer = self._resolve_printer()
            if current_printer is None:
                if job_type == "kick_drawer":
                    # The drawer is wired through the receipt printer: no
                    # printer, no drawer. Stay silent -- every cash sale
                    # queues one, and nothing waits on it.
                    logger.debug("No receipt printer configured — skipping drawer kick.")
                    continue
                logger.warning("No receipt printer configured — skipping %s job.", job_type)
                self.error_occurred.emit(printer_not_configured_message())
                continue

            try:
                if not current_printer.connect():
                    msg = "Printer not available — skipping %s job. Check printer settings in Settings > Hardware."
                    logger.warning(msg, job_type)
                    self.error_occurred.emit(_t("printer.not_available"))
                    continue

                if job_type == "kick_drawer":
                    # Check drawer_on_cash_only config
                    drawer_cash_only = bool(ConfigService.get("drawer_on_cash_only"))
                    if drawer_cash_only:
                        # data = list of payment method strings
                        if not data:
                            logger.info("Drawer skipped — no payment methods provided (drawer_on_cash_only=True)")
                            continue
                        has_cash = any(isinstance(m, str) and m.strip().upper() == "CASH" for m in data)
                        if not has_cash:
                            logger.info("Drawer skipped — no cash payment (drawer_on_cash_only=True)")
                            continue
                    current_printer.kick_drawer()
                elif job_type == "print_receipt":
                    current_printer.print_commands(data)

                current_printer.disconnect()
                self.job_completed.emit()

            except Exception as e:
                logger.error("Print job '%s' failed: %s", job_type, e)
                self.error_occurred.emit(str(e))

            time.sleep(0.1)

    def _resolve_printer(self) -> IPrinter | None:
        """Pick the printer for the next job: the injected one, the real
        driver if settings name one, else None (no printer configured)."""
        if self.printer:
            return self.printer

        if receipt_printer_configured():
            return ESCPOSDriver()

        return None
