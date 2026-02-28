import logging
import logging.handlers
import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
from cbpos.config import Config
from cbpos.infrastructure.resource_loader import ResourceLoader
from cbpos.ui.main_window import MainWindow


def setup_logging() -> None:
    """
    Configure file-based logging for the application.

    Writes WARNING+ messages to logs/cbpos.log with rotation
    (5 MB max, 3 backups). Console output remains unchanged.
    """
    log_dir = Config.BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "cbpos.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"))

    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    # Ensure root logger level allows WARNING+ through
    if root_logger.level > logging.WARNING or root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.WARNING)


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
    Font loading MUST happen before any UI is created to prevent fallback to
    system fonts.
    """
    # Set up file-based error logging
    setup_logging()

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

    # Initialize Theme (Load from settings or default to Dark)
    from cbpos.core.services.theme_service import ThemeService
    from cbpos.core.services.config_service import ConfigService

    # Inject stylesheet handler so ThemeService doesn't need PyQt imports
    ThemeService.set_stylesheet_handler(lambda css: app.setStyleSheet(css))
    saved_theme = ConfigService.get("theme")  # Returns "Dark" by default
    ThemeService.apply_theme(saved_theme)

    # Inject translator handlers so LanguageService doesn't need PyQt imports
    from PyQt6.QtCore import QTranslator
    from cbpos.core.services.language_service import LanguageService

    LanguageService.set_translator_handlers(
        create=QTranslator,
        install=lambda t: app.installTranslator(t),
        remove=lambda t: app.removeTranslator(t),
    )

    # Register Reports
    from cbpos.core.reports import register_all_reports

    register_all_reports()
    print("[BOOTSTRAP] Reports registered.")

    # First-Run Setup Wizard
    if not os.path.exists(ConfigService.SETTINGS_FILE):
        from cbpos.ui.dialogs.setup_wizard import SetupWizard

        print("[BOOTSTRAP] First run detected - launching setup wizard...")
        wizard = SetupWizard()
        if not wizard.exec():
            print("[BOOTSTRAP] Setup wizard cancelled. Exiting.")
            sys.exit(0)

    # Start scheduler timer for auto-report
    if ConfigService.get("auto_report_enabled"):
        try:
            from PyQt6.QtCore import QTimer
            from cbpos.core.services.scheduler_service import SchedulerService

            scheduler_timer = QTimer(app)
            scheduler_timer.timeout.connect(SchedulerService.check_automation)
            scheduler_timer.start(60_000)  # Check every 60 seconds
            print("[BOOTSTRAP] Scheduler started.")
        except Exception as e:
            print(f"[BOOTSTRAP] Scheduler failed to start: {e}")

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
