import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
from cbpos.infrastructure.resource_loader import ResourceLoader
from cbpos.ui.main_window import MainWindow


def qt_message_handler(mode: QtMsgType, context, message: str):
    """
    Custom Qt message handler to filter out internal Qt warnings.

    Suppresses:
    - "OpenType support missing" warnings (internal Qt rendering)
    - Script-related warnings (script 20, script 16, etc.)

    Allows all other messages through to help debug real errors.
    """
    # Suppress OpenType and script warnings (these are internal Qt noise)
    if "OpenType support missing" in message:
        return
    if "script 20" in message or "script 16" in message:
        return

    # Allow all other messages through
    if mode == QtMsgType.QtDebugMsg:
        print(f"[Qt Debug] {message}")
    elif mode == QtMsgType.QtWarningMsg:
        print(f"[Qt Warning] {message}")
    elif mode == QtMsgType.QtCriticalMsg:
        print(f"[Qt Critical] {message}")
    elif mode == QtMsgType.QtFatalMsg:
        print(f"[Qt Fatal] {message}")


def main():
    """
    Application entry point.

    Initializes Qt application, loads resources, and launches the main window.
    Font loading MUST happen before any UI is created to prevent fallback to system fonts.
    """
    # Install custom message handler to suppress Qt internal warnings
    qInstallMessageHandler(qt_message_handler)

    # Ensure high DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("CB POS")

    # Install Global Input Manager
    from cbpos.infrastructure.input_manager import InputManager

    input_manager = InputManager()
    app.installEventFilter(input_manager)

    # CRITICAL: Load fonts BEFORE any UI is created
    print("[BOOTSTRAP] Loading application resources...")
    primary_font_family = ResourceLoader.load_fonts()

    # Force the application-wide default font
    default_font = QFont(primary_font_family, 10)
    app.setFont(default_font)
    print(f"[BOOTSTRAP] Application font set to: {primary_font_family}")

    # Register Reports
    from cbpos.core.reports import register_all_reports

    register_all_reports()
    print("[BOOTSTRAP] Reports registered.")

    # Launch main window
    window = MainWindow()
    window.showMaximized()  # Industrial apps usually run full screen

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
