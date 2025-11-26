import time
from PyQt6.QtCore import QThread
from cbpos.core.interfaces.iprinter import IPrinter
from cbpos.core.services.config_service import ConfigService
from escpos.printer import Usb, Network
from PIL import Image


class MockPrinter(IPrinter):
    """
    Mock Printer for development/testing without hardware.
    """

    def connect(self) -> bool:
        print("[MockPrinter] Connected")
        return True

    def disconnect(self):
        print("[MockPrinter] Disconnected")

    def print_text(self, text: str):
        print(f"[MockPrinter] {text}", end="")

    def print_line(self, text: str):
        print(f"[MockPrinter] {text}")

    def cut(self):
        print("[MockPrinter] CUT")

    def kick_drawer(self):
        print("[MockPrinter] KICK DRAWER")

    def print_image(self, image: Image.Image):
        print(f"[MockPrinter] Printing Image: {image.size}")


class ESCPOSDriver(IPrinter):
    """
    Real implementation using python-escpos.
    """

    def __init__(self):
        self.printer = None

    def connect(self) -> bool:
        settings = ConfigService.get_all()
        p_type = settings.get("printer_type", "MOCK")
        p_path = settings.get("printer_path", "")

        try:
            if p_type == "USB":
                # Auto-detect or specific
                # For now, we'll try to find the first USB printer if no path (VID:PID) is given
                # This is a simplification. In production, we need VID:PID.
                # Example path format: "0x04b8:0x0202"
                if p_path and ":" in p_path:
                    vid, pid = p_path.split(":")
                    self.printer = Usb(int(vid, 16), int(pid, 16))
                else:
                    # Fallback to Dummy if no VID:PID provided for now
                    # Real auto-detection requires scanning USB bus
                    print(
                        "USB Printer requires VID:PID in settings (e.g., 0x04b8:0x0202)"
                    )
                    return False
            elif p_type == "NETWORK":
                if p_path:
                    self.printer = Network(p_path)
                else:
                    print("Network Printer requires IP address")
                    return False
            else:
                # MOCK or unknown
                return False

            return True
        except Exception as e:
            print(f"Printer Connection Failed: {e}")
            return False

    def disconnect(self):
        if self.printer:
            self.printer.close()

    def print_text(self, text: str):
        if self.printer:
            self.printer.text(text)

    def print_line(self, text: str):
        if self.printer:
            self.printer.text(text + "\n")

    def cut(self):
        if self.printer:
            self.printer.cut()

    def kick_drawer(self):
        if self.printer:
            self.printer.cashdraw(2)

    def print_image(self, image: Image.Image):
        if self.printer:
            self.printer.image(image)


class PrintWorker(QThread):
    """
    Worker thread to handle printing tasks asynchronously.
    """

    def __init__(self, printer: IPrinter = None):
        super().__init__()
        self.printer = printer
        self.queue = []
        self.running = True

    def add_job(self, job_type: str, data: any = None):
        """
        Add a job to the queue.
        job_type: 'print_receipt', 'kick_drawer', 'print_image'
        """
        self.queue.append((job_type, data))
        if not self.isRunning():
            self.start()

    def run(self):
        while self.running and self.queue:
            job_type, data = self.queue.pop(0)

            # Determine printer to use
            settings = ConfigService.get_all()
            p_type = settings.get("printer_type", "MOCK")

            current_printer = self.printer

            if not current_printer:
                if p_type == "MOCK":
                    current_printer = MockPrinter()
                else:
                    current_printer = ESCPOSDriver()

            try:
                if current_printer.connect():
                    if job_type == "kick_drawer":
                        current_printer.kick_drawer()
                    elif job_type == "print_receipt":
                        current_printer.print_text(data)
                        current_printer.cut()
                    elif job_type == "print_image":
                        current_printer.print_image(data)
                        current_printer.cut()

                    current_printer.disconnect()
                else:
                    # Fallback to Mock if real printer fails
                    print("Real printer failed. Falling back to Mock.")
                    mock = MockPrinter()
                    mock.connect()
                    if job_type == "print_receipt":
                        mock.print_text(data)
                    elif job_type == "print_image":
                        mock.print_image(data)
                    mock.disconnect()

            except Exception as e:
                print(f"Print Job Failed: {e}")

            time.sleep(0.1)  # Small delay between jobs
