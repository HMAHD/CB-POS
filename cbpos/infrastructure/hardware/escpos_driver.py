import logging
import queue
import time
from typing import List, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal

from cbpos.core.interfaces.iprinter import IPrinter
from cbpos.core.services.config_service import ConfigService
from escpos.printer import Usb, Network
from PIL import Image

logger = logging.getLogger(__name__)


class NullPrinter(IPrinter):
    """
    No-op printer used when no hardware is configured.

    Silently discards all commands — no console output, no side effects.
    Used during development or when the shop has not yet set up a printer.
    """

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def print_text(self, text: str) -> None:
        pass

    def print_line(self, text: str) -> None:
        pass

    def cut(self) -> None:
        pass

    def print_commands(self, commands: List[Dict[str, Any]]) -> None:
        pass

    def kick_drawer(self) -> None:
        pass


class ESCPOSDriver(IPrinter):
    """Real ESC/POS implementation using python-escpos for USB and Network printers."""

    def __init__(self) -> None:
        self.printer = None

    def connect(self) -> bool:
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
        if self.printer:
            try:
                self.printer.close()
            except Exception as e:
                logger.debug("Printer disconnect error (non-critical): %s", e)

    def print_text(self, text: str) -> None:
        if self.printer:
            self.printer.text(text)

    def print_line(self, text: str) -> None:
        if self.printer:
            self.printer.text(text + "\n")

    def cut(self) -> None:
        if self.printer:
            self.printer.cut()

    def print_commands(self, commands: List[Dict[str, Any]]) -> None:
        if not self.printer:
            return

        for cmd in commands:
            try:
                c_type = cmd.get("type")

                if c_type == "text":
                    align = cmd.get("align", "left").upper()
                    self.printer.set(align=align)
                    self.printer.text(cmd.get("val") + "\n")

                elif c_type == "image":
                    path = cmd.get("path")
                    if path:
                        try:
                            img = Image.open(path)
                            max_width = ConfigService.get_int("printer_image_max_width", 500)
                            if img.width > max_width:
                                ratio = max_width / img.width
                                new_height = int(img.height * ratio)
                                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                            self.printer.image(img)
                        except Exception as e:
                            logger.error("Failed to print image: %s", e)

                elif c_type == "barcode":
                    code = cmd.get("val")
                    bc_type = cmd.get("code", "CODE39")
                    try:
                        self.printer.barcode(code, bc_type, function_type="B")
                    except Exception as e:
                        logger.error("Failed to print barcode: %s", e)

                elif c_type == "feed":
                    lines = cmd.get("lines", 1)
                    self.printer.text("\n" * lines)

                elif c_type == "cut":
                    self.printer.cut()

            except Exception as e:
                logger.error("Error processing print command %s: %s", cmd.get("type"), e)

    def kick_drawer(self) -> None:
        if self.printer:
            self.printer.cashdraw(2)


class PrintWorker(QThread):
    """Background thread for asynchronous print job processing.

    Resolves the printer once per run cycle from application settings:
    - printer_type == "NONE" → NullPrinter (silent no-op)
    - printer_type == "USB" / "NETWORK" → ESCPOSDriver (real hardware)

    If the real printer fails to connect, the job is skipped and the failure
    is logged — no silent fallback to a mock that pollutes stdout.
    """

    error_occurred = pyqtSignal(str)  # Emitted when a print job fails

    def __init__(self, printer: IPrinter | None = None) -> None:
        super().__init__()
        self.printer = printer
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.running = True

    def add_job(self, job_type: str, data: Any = None) -> None:
        """Queue a print job. Starts the thread if not already running.

        Args:
            job_type: 'print_receipt' or 'kick_drawer'
            data: Command list for print_receipt, None for kick_drawer
        """
        self._queue.put((job_type, data))
        if not self.isRunning():
            self.start()

    def stop(self) -> None:
        """Signal the worker to stop after current job completes."""
        self.running = False

    def run(self) -> None:
        while self.running:
            try:
                job_type, data = self._queue.get(timeout=1)
            except queue.Empty:
                if not self.running:
                    break
                continue

            current_printer = self._resolve_printer()

            try:
                if not current_printer.connect():
                    logger.warning(
                        "Printer not available — skipping %s job. " "Check printer settings in Settings > Hardware.",
                        job_type,
                    )
                    continue

                if job_type == "kick_drawer":
                    current_printer.kick_drawer()
                elif job_type == "print_receipt":
                    current_printer.print_commands(data)

                current_printer.disconnect()

            except Exception as e:
                logger.error("Print job '%s' failed: %s", job_type, e)
                self.error_occurred.emit(str(e))

            time.sleep(0.1)

    def _resolve_printer(self) -> IPrinter:
        """Determine which printer implementation to use from settings."""
        if self.printer:
            return self.printer

        settings = ConfigService.get_all()
        p_type = settings.get("printer_type", "NONE")

        if p_type in ("USB", "NETWORK"):
            return ESCPOSDriver()

        return NullPrinter()
