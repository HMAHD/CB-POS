from PyQt6.QtCore import QEvent, QObject, QTimer


class InputManager(QObject):
    """
    Global Input Manager to handle:
    1. Enter Key Routing (Login, Sales, Dialogs)
    2. Scanner Input Routing (Bypassing focus issues)
    3. Preventing "Focus Fighting" by managing state
    """

    def __init__(self):
        """Initialize scanner buffer state and the inter-keystroke timeout timer."""
        super().__init__()
        self.current_view = None
        self.scanner_buffer = ""
        self.scanner_timer = QTimer()
        self.scanner_timer.setSingleShot(True)
        self.scanner_timer.timeout.connect(self.clear_scanner_buffer)

    def clear_scanner_buffer(self):
        """Clear the scanner input buffer (called when the inter-key timer expires)."""
        self.scanner_buffer = ""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Accumulate printable keystrokes into the scanner buffer.

        The buffer resets after a 50ms gap, which is enough to tell a
        scanner's rapid-fire burst apart from normal human typing. Enter
        handling was intentionally removed here (moved to individual
        views); this filter never consumes events itself.
        """
        if event.type() == QEvent.Type.KeyPress:
            # Handle Scanner Input (Fast bursts)
            if event.text():
                self.scanner_buffer += event.text()
                self.scanner_timer.start(50)  # 50ms timeout

            # 1. Handle Enter Key - REMOVED (Decentralized to Views)
            # if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            #     return self.handle_enter_key(obj)

        return super().eventFilter(obj, event)
