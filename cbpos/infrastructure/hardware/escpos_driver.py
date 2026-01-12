import time
from typing import List, Dict, Any
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

    def print_commands(self, commands: List[Dict[str, Any]]):
        for cmd in commands:
            c_type = cmd.get("type")
            if c_type == "text":
                print(f"[MockPrinter] TEXT ({cmd.get('align', 'left')}): {cmd.get('val')}")
            elif c_type == "image":
                print(f"[MockPrinter] IMAGE: {cmd.get('path')}")
            elif c_type == "barcode":
                print(f"[MockPrinter] BARCODE: {cmd.get('val')} ({cmd.get('code')})")
            elif c_type == "feed":
                print(f"[MockPrinter] FEED: {cmd.get('lines')} lines")
            elif c_type == "cut":
                print("[MockPrinter] CUT")

    def kick_drawer(self):
        print("[MockPrinter] KICK DRAWER")


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
                if p_path and ":" in p_path:
                    vid, pid = p_path.split(":")
                    self.printer = Usb(int(vid, 16), int(pid, 16))
                else:
                    print("USB Printer requires VID:PID in settings (e.g., 0x04b8:0x0202)")
                    return False
            elif p_type == "NETWORK":
                if p_path:
                    self.printer = Network(p_path)
                else:
                    print("Network Printer requires IP address")
                    return False
            else:
                return False

            return True
        except Exception as e:
            print(f"Printer Connection Failed: {e}")
            return False

    def disconnect(self):
        if self.printer:
            self.printer.close()

    def print_commands(self, commands: List[Dict[str, Any]]):
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
                            # Resize if too wide (max 500px usually safe for 80mm)
                            max_width = ConfigService.get_int("printer_image_max_width", 500)
                            if img.width > max_width:
                                ratio = max_width / img.width
                                new_height = int(img.height * ratio)
                                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                            self.printer.image(img)
                        except Exception as e:
                            print(f"Failed to print image: {e}")

                elif c_type == "barcode":
                    code = cmd.get("val")
                    bc_type = cmd.get("code", "CODE39")
                    try:
                        self.printer.barcode(code, bc_type, function_type="B")
                    except Exception as e:
                        print(f"Failed to print barcode: {e}")

                elif c_type == "feed":
                    lines = cmd.get("lines", 1)
                    self.printer.text("\n" * lines)

                elif c_type == "cut":
                    self.printer.cut()

            except Exception as e:
                print(f"Error processing command {cmd}: {e}")

    def kick_drawer(self):
        if self.printer:
            self.printer.cashdraw(2)


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
        job_type: 'print_receipt' (data=commands), 'kick_drawer'
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
                        # data is now a list of commands
                        current_printer.print_commands(data)

                    current_printer.disconnect()
                else:
                    # Fallback to Mock if real printer fails
                    print("Real printer failed. Falling back to Mock.")
                    mock = MockPrinter()
                    mock.connect()
                    if job_type == "print_receipt":
                        mock.print_commands(data)
                    elif job_type == "kick_drawer":
                        mock.kick_drawer()
                    mock.disconnect()

            except Exception as e:
                print(f"Print Job Failed: {e}")

            time.sleep(0.1)  # Small delay between jobs
