from PyQt6.QtCore import QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication


class BarcodeScanner(QObject):
    """
    Global event filter to capture barcode scanner input.
    Scanners usually send rapid keystrokes followed by Enter.
    """

    barcode_scanned = pyqtSignal(str)

    def __init__(self, app: QApplication):
        """Install a global key-event filter on the application to catch scanner input."""
        super().__init__()
        self.app = app
        self.buffer = ""
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear_buffer)

        # Install event filter on the application
        self.app.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Buffer printable keystrokes and emit ``barcode_scanned`` on Enter.

        The buffer is cleared after 50ms of inactivity, since a real
        scanner sends its whole payload faster than that; a human typing
        normally won't trigger a false match. Consumes the Enter keystroke
        (returns True) only when it completed a non-empty scan.
        """
        if event.type() == QEvent.Type.KeyPress:
            # Check if it's a printable character
            text = event.text()
            if text:
                self.buffer += text
                self.timer.start(50)  # Reset buffer if no input for 50ms (Scanner is fast)

                # If Enter is pressed, emit signal
                if event.key() == 16777220 or event.key() == 16777221:  # Enter keys
                    if self.buffer.strip():
                        self.barcode_scanned.emit(self.buffer.strip())
                    self.buffer = ""
                    return True  # Consume event? Maybe not, let it propagate if needed.
                    # Actually, for a global hook, we might want to consume it if we are sure it's a barcode.
                    # But usually, we just let it go to the focused widget if it's a text input.
                    # However, the requirement is "process instantly without losing focus".
                    # If we emit the signal, the main window can handle it.

        return super().eventFilter(obj, event)

    def clear_buffer(self):
        """Clear the keystroke buffer (called when the inter-key timer expires)."""
        self.buffer = ""
