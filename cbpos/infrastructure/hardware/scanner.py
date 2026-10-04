from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit


class BarcodeScanner(QObject):
    """
    Global event filter to capture barcode scanner input.
    Scanners usually send rapid keystrokes followed by Enter.
    """

    barcode_scanned = pyqtSignal(str)

    # ponytail: fixed threshold; a fast typist's 1-2 keys + Enter inside the
    # 50ms window stay plain Enter. Make configurable if shops use <3-char codes.
    MIN_SCAN_LENGTH = 3

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
        (returns True) only when it completed a scanner burst of at least
        ``MIN_SCAN_LENGTH`` characters while focus is NOT in a text field;
        any other Enter reaches the focused widget so ``returnPressed``
        fires normally (#546).
        """
        # App-level filters see each key twice (QWindow, then the focused
        # widget); count only the widget copy or every char doubles.
        if event.type() == QEvent.Type.KeyPress and obj.isWidgetType():
            if event.key() in (Qt.Key.Key_Return.value, Qt.Key.Key_Enter.value):
                barcode = self.buffer.strip()
                self.buffer = ""
                if len(barcode) >= self.MIN_SCAN_LENGTH and not self._is_text_input(obj):
                    self.barcode_scanned.emit(barcode)
                    return True
            elif event.text():
                self.buffer += event.text()
                self.timer.start(50)  # Reset buffer if no input for 50ms (Scanner is fast)

        return super().eventFilter(obj, event)

    @staticmethod
    def _is_text_input(widget) -> bool:
        """True if ``widget`` is an editable text field that handles its own Enter.

        A scan typed into such a field is submitted by the field's own
        ``returnPressed`` (Sales search, Stock Take add, scanner test, ...),
        so it must not also be routed to the active view.
        """
        if isinstance(widget, QLineEdit):
            return not widget.isReadOnly()
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            return not widget.isReadOnly()
        return False

    def clear_buffer(self):
        """Clear the keystroke buffer (called when the inter-key timer expires)."""
        self.buffer = ""
