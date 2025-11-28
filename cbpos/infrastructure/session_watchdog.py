from PyQt6.QtCore import QObject, QTimer, QEvent, pyqtSignal
from PyQt6.QtWidgets import QApplication


class SessionWatchdog(QObject):
    """
    Monitors user activity and signals when the session expires.
    """

    session_expired = pyqtSignal()

    def __init__(self, timeout_minutes=5, parent=None):
        super().__init__(parent)
        self.timeout_ms = timeout_minutes * 60 * 1000
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timeout)

        self._monitoring = False

    def start_monitoring(self):
        """Start monitoring user activity."""
        if not self._monitoring:
            QApplication.instance().installEventFilter(self)
            self.timer.start(self.timeout_ms)
            self._monitoring = True

    def stop_monitoring(self):
        """Stop monitoring."""
        if self._monitoring:
            QApplication.instance().removeEventFilter(self)
            self.timer.stop()
            self._monitoring = False

    def eventFilter(self, obj, event):
        """Intercept events to reset the timer."""
        if self._monitoring:
            if event.type() in (
                QEvent.Type.MouseMove,
                QEvent.Type.KeyPress,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.TouchBegin,
            ):
                self.reset_timer()

        return super().eventFilter(obj, event)

    def reset_timer(self):
        """Reset the inactivity timer."""
        if self._monitoring:
            self.timer.start(self.timeout_ms)

    def on_timeout(self):
        """Handle session timeout."""
        self.stop_monitoring()

        # Log Timeout
        try:
            from cbpos.core.services.auth_service import AuthService
            from cbpos.core.database import Database
            from cbpos.core.models import AuditLog

            user = AuthService.get_current_user()
            if user:
                db = Database()
                with db.get_session() as session:
                    log = AuditLog(
                        user_id=user.id,
                        action="Session Timeout",
                        event_type="TIMEOUT",
                        terminal_id="TERM-01",
                        details="Auto-logout due to inactivity",
                    )
                    session.add(log)
                    session.commit()
        except Exception:
            pass

        self.session_expired.emit()
