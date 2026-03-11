import logging
import logging.handlers
import shutil
import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
from cbpos.config import Config
from cbpos.infrastructure.resource_loader import ResourceLoader
from cbpos.ui.main_window import MainWindow


# Buffer for early messages emitted before the logging system is ready.
# Flushed to the logger by ``_flush_early_log()`` after ``setup_logging()``.
_early_log: list[str] = []


def _flush_early_log() -> None:
    """Write buffered early messages to the application logger."""
    _logger = logging.getLogger("cbpos.bootstrap")
    for msg in _early_log:
        _logger.warning(msg)
    _early_log.clear()


def ensure_data_dir() -> None:
    """Create the user data directory and migrate legacy data if needed.

    On first launch after an update that moves data to AppData, this
    copies cbpos.db, settings.json, and .encryption_key from the old
    install-relative location to the new platform-specific DATA_DIR.
    """
    data_dir = Config.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    # Only migrate when running as an installed app (frozen) and the
    # new data dir does not yet have a database.
    if not getattr(sys, "frozen", False):
        return

    new_db = data_dir / "cbpos.db"
    if new_db.exists():
        return  # Already migrated or fresh install with DB created

    # Look for legacy data next to the executable (old install layout).
    exe_dir = Path(sys.executable).parent
    legacy_db = exe_dir / "cbpos.db"
    if not legacy_db.exists():
        return  # Truly fresh install, nothing to migrate

    _early_log.append("Migrating user data to %s" % data_dir)
    for filename in ("cbpos.db", "settings.json", ".encryption_key"):
        src = exe_dir / filename
        dst = data_dir / filename
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(str(src), str(dst))
                _early_log.append("Migrated %s" % filename)
            except OSError as e:
                _early_log.append("WARNING: Could not copy %s: %s" % (filename, e))

    # Migrate product images
    legacy_images = exe_dir / "cbpos" / "assets" / "products"
    new_images = data_dir / "product_images"
    if legacy_images.exists() and not new_images.exists():
        try:
            shutil.copytree(str(legacy_images), str(new_images))
            _early_log.append("Migrated product images")
        except OSError as e:
            _early_log.append("WARNING: Could not copy product images: %s" % e)

    _early_log.append("Data migration complete.")


def setup_logging() -> None:
    """
    Configure file-based logging for the application.

    Writes WARNING+ messages to logs/cbpos.log with rotation
    (5 MB max, 3 backups). Console output remains unchanged.
    """
    log_dir = Config.DATA_DIR / "logs"
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
    # Ensure user data directory exists and migrate legacy data if needed
    ensure_data_dir()

    # Create a named mutex so the Inno Setup installer can detect a running instance.
    # On non-Windows this is harmless — ctypes.windll doesn't exist.
    try:
        import ctypes

        ctypes.windll.kernel32.CreateMutexW(None, False, "CBPOSAppMutex")
    except (AttributeError, OSError):
        pass  # Not on Windows — skip

    # Set up file-based error logging
    setup_logging()
    _flush_early_log()

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

    # Set application language from saved config
    from cbpos.i18n import set_language

    saved_language = ConfigService.get("language") or "en"
    set_language(saved_language)

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

    # First-Run Database Setup (empty vs demo)
    from cbpos.core.services.database_setup_service import DatabaseSetupService

    if DatabaseSetupService.needs_setup():
        from cbpos.ui.dialogs.database_setup_dialog import DatabaseSetupDialog

        print("[BOOTSTRAP] No database found - showing database setup dialog...")
        db_dialog = DatabaseSetupDialog()
        if not db_dialog.exec():
            print("[BOOTSTRAP] Database setup cancelled. Exiting.")
            sys.exit(0)

        if db_dialog.choice == DatabaseSetupDialog.CHOICE_DEMO:
            print("[BOOTSTRAP] Creating demo database...")
            DatabaseSetupService.create_demo_database()
            print("[BOOTSTRAP] Demo database ready.")
        else:
            print("[BOOTSTRAP] Creating empty database...")
            DatabaseSetupService.create_empty_database()
            print("[BOOTSTRAP] Empty database ready.")

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

    # Check for updates 3 seconds after startup (non-blocking).
    # The thread reference is kept on the app object to prevent GC.
    from PyQt6.QtCore import QTimer
    from cbpos.ui.dialogs.update_dialog import check_for_updates_async

    def _deferred_update_check():
        app._update_thread = check_for_updates_async(parent=window, silent=True)

    QTimer.singleShot(3000, _deferred_update_check)

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
