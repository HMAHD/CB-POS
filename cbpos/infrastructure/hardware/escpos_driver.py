import time
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from cbpos.core.interfaces.iprinter import IPrinter

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
        print(f"[MockPrinter] {text}", end='')

    def print_line(self, text: str):
        print(f"[MockPrinter] {text}")

    def cut(self):
        print("[MockPrinter] CUT")

    def kick_drawer(self):
        print("[MockPrinter] KICK DRAWER")

class ESCPOSDriver(IPrinter):
    """
    Real implementation using python-escpos.
    For now, we will default to MockPrinter if python-escpos is not installed or configured.
    """
    def __init__(self):
        self.printer = None

    def connect(self) -> bool:
        try:
            # TODO: Load config to determine printer type (USB, Network, Serial)
            # For now, we'll try to use a Dummy printer or fail gracefully
            # from escpos.printer import Usb
            # self.printer = Usb(0x04b8, 0x0202) # Example Vendor/Product ID
            return False # Not implemented yet
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

class PrintWorker(QThread):
    """
    Worker thread to handle printing tasks asynchronously.
    """
    def __init__(self, printer: IPrinter = None):
        super().__init__()
        self.printer = printer or MockPrinter()
        self.queue = []
        self.running = True

    def add_job(self, job_type: str, data: any = None):
        """
        Add a job to the queue.
        job_type: 'print_receipt', 'kick_drawer'
        """
        self.queue.append((job_type, data))
        if not self.isRunning():
            self.start()

    def run(self):
        while self.running and self.queue:
            job_type, data = self.queue.pop(0)
            try:
                if not self.printer.connect():
                    # If real printer fails, maybe fallback to mock or log error
                    if not isinstance(self.printer, MockPrinter):
                         print("Printer connection failed. Using Mock.")
                         self.printer = MockPrinter()
                         self.printer.connect()

                if job_type == 'kick_drawer':
                    self.printer.kick_drawer()
                elif job_type == 'print_receipt':
                    # data is the formatted receipt string
                    self.printer.print_text(data)
                    self.printer.cut()
                
                self.printer.disconnect()
            except Exception as e:
                print(f"Print Job Failed: {e}")
            
            time.sleep(0.1) # Small delay between jobs
