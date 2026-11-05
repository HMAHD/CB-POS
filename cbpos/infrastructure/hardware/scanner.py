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

    # Set True on a text field that must never receive a scan as input (a
    # quantity cell editor): a burst + Enter there is routed as a scan and
    # the view discards the typed digits, instead of committing a barcode
    # as a quantity (#547). Human Enter still reaches the field.
    SCAN_PASSTHROUGH_PROPERTY = "scanPassthrough"

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
        fires normally (#546). Such an Enter also claims its shortcut
        override, so an Enter shortcut on the focused widget doesn't take
        it first (#548).
        """
        # A scan's Enter must not fire an Enter shortcut on the focused
        # widget (Stock Take History's Enter-to-open, #548/#594): Qt offers
        # a key to shortcuts before delivering it, so claim the override
        # and let the KeyPress below route the scan. Not while a modal
        # dialog is up: its Enter shortcut (payment, quantity) keeps the
        # key rather than a scan reaching the view behind it.
        if event.type() == QEvent.Type.ShortcutOverride and obj.isWidgetType():
            if (
                event.key() in (Qt.Key.Key_Return.value, Qt.Key.Key_Enter.value)
                and QApplication.activeModalWidget() is None
                and self._completes_scan(obj)
            ):
                event.accept()
                return True
        # App-level filters see each key twice (QWindow, then the focused
        # widget); count only the widget copy or every char doubles.
        if event.type() == QEvent.Type.KeyPress and obj.isWidgetType():
            if event.key() in (Qt.Key.Key_Return.value, Qt.Key.Key_Enter.value):
                barcode = self.buffer.strip()
                is_scan = self._completes_scan(obj) and QApplication.activeModalWidget() is None
                self.buffer = ""
                if is_scan:
                    self.barcode_scanned.emit(barcode)
                    return True
            elif event.text():
                self.buffer += event.text()
                self.timer.start(50)  # Reset buffer if no input for 50ms (Scanner is fast)

        return super().eventFilter(obj, event)

    def _completes_scan(self, widget) -> bool:
        """True if an Enter now ends a scanner burst that should be routed as a scan.

        That is a buffer of at least ``MIN_SCAN_LENGTH`` characters, with
        focus outside a text field that submits scans itself.
        """
        return len(self.buffer.strip()) >= self.MIN_SCAN_LENGTH and not self._is_text_input(widget)

    @staticmethod
    def _is_text_input(widget) -> bool:
        """True if ``widget`` is an editable text field that handles its own Enter.

        A scan typed into such a field is submitted by the field's own
        ``returnPressed`` (Sales search, Stock Take add, scanner test, ...),
        so it must not also be routed to the active view. Fields marked
        with ``SCAN_PASSTHROUGH_PROPERTY`` don't count as text input.
        """
        if widget.property(BarcodeScanner.SCAN_PASSTHROUGH_PROPERTY):
            return False
        if isinstance(widget, QLineEdit):
            return not widget.isReadOnly()
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            return not widget.isReadOnly()
        return False

    def clear_buffer(self):
        """Clear the keystroke buffer (called when the inter-key timer expires)."""
        self.buffer = ""
