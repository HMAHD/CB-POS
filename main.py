import logging
import logging.handlers
import os
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QtMsgType, qInstallMessageHandler
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QApplication

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


def _report_crash(exc_type, exc_value, exc_traceback) -> None:
    """Log an uncaught exception and show a crash dialog if possible.

    Installed as ``sys.excepthook`` so a crash on the packaged Windows
    build (built with ``console=False`` in cbpos.spec) is never silently
    swallowed -- printing to stdout alone writes to a console that doesn't
    exist there. Also used as the fallback for exceptions raised before
    ``sys.excepthook`` is installed (e.g. during ``ensure_data_dir()``).
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    try:
        logging.getLogger("cbpos.crash").critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    except Exception:
        # Logging isn't configured yet (crash happened before setup_logging()) --
        # fall back to stderr, which at least helps when running from a console.
        import traceback

        traceback.print_exception(exc_type, exc_value, exc_traceback)

    app = QApplication.instance()
    if app is not None:
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "CB POS",
            "CB POS encountered an unexpected error and needs to close.\n\nDetails were saved to the logs folder.",
        )


def run_migrations() -> str | None:
    """Apply pending Alembic migrations to bring the database schema up to date.

    For databases created via ``Base.metadata.create_all()`` (first-run) that
    were never stamped by Alembic, this stamps them at ``head`` so future
    migrations apply cleanly.  For databases already tracked, it runs
    ``alembic upgrade head`` to apply any new migrations.

    Safe to call on every startup — if the DB is already at head, this is a
    fast no-op.

    Returns:
        None on success, or the error message if migration failed -- the
        caller must not continue on an out-of-date schema (#630).
    """
    from cbpos.config import Config

    db_path = Config.DATA_DIR / "cbpos.db"
    if not db_path.exists():
        return None  # No database yet — will be created by DatabaseSetupService

    try:
        from alembic.config import Config as AlembicConfig
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, inspect

        from alembic import command

        alembic_cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", Config.DB_URI)
        # Don't let env.py fileConfig() over our logging (logging.config isn't bundled, #630).
        alembic_cfg.attributes["configure_logger"] = False

        engine = create_engine(Config.DB_URI)

        # Check if alembic_version table exists
        inspector = inspect(engine)
        has_version_table = "alembic_version" in inspector.get_table_names()

        if not has_version_table:
            # Database was created by create_all() without Alembic tracking.
            # Stamp at head so future migrations apply correctly.
            command.stamp(alembic_cfg, "head")
            _early_log.append("Database stamped at current migration head.")
        else:
            # Check if there are pending migrations
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                current_rev = context.get_current_heads()

            script = ScriptDirectory.from_config(alembic_cfg)
            head_rev = script.get_current_head()

            if not current_rev or head_rev not in current_rev:
                command.upgrade(alembic_cfg, "head")
                _early_log.append("Database migrated to latest schema.")

        engine.dispose()

    except Exception as e:
        _early_log.append(f"ERROR: Auto-migration failed: {e}")
        return str(e)
    return None


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

    _early_log.append(f"Migrating user data to {data_dir}")
    for filename in ("cbpos.db", "settings.json", ".encryption_key"):
        src = exe_dir / filename
        dst = data_dir / filename
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(str(src), str(dst))
                _early_log.append(f"Migrated {filename}")
            except OSError as e:
                _early_log.append(f"WARNING: Could not copy {filename}: {e}")

    # Migrate product images
    legacy_images = exe_dir / "cbpos" / "assets" / "products"
    new_images = data_dir / "product_images"
    if legacy_images.exists() and not new_images.exists():
        try:
            shutil.copytree(str(legacy_images), str(new_images))
            _early_log.append("Migrated product images")
        except OSError as e:
            _early_log.append(f"WARNING: Could not copy product images: {e}")

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

    # Apply any pending database schema migrations
    migration_error = run_migrations()
    if "--migrate-only" in sys.argv:  # CI smoke test of the frozen exe (#630)
        sys.exit(1 if migration_error else 0)

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

    # Route uncaught exceptions to the log + a crash dialog instead of a
    # stdout that doesn't exist on the packaged (console=False) build.
    sys.excepthook = _report_crash

    # Install custom message handler to suppress Qt internal warnings
    qInstallMessageHandler(qt_message_handler)

    # Ensure high DPI scaling and consistent fractional display scaling across platforms (#600)
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("CB POS")

    # Install Global Input Manager
    from cbpos.infrastructure.input_manager import InputManager

    input_manager = InputManager()
    app.installEventFilter(input_manager)

    # CRITICAL: Load fonts BEFORE any UI is created
    print("[BOOTSTRAP] Loading application resources...")
    primary_font_family = ResourceLoader.load_fonts()

    # Force the application-wide default font with full script fallback
    default_font = QFont(primary_font_family, 10)
    default_font.setFamilies(ResourceLoader.get_font_families())
    app.setFont(default_font)
    print(f"[BOOTSTRAP] Application font set to: {primary_font_family} with fallbacks {default_font.families()}")

    # Initialize Theme (Load from settings or default to Dark)
    from cbpos.core.services.config_service import ConfigService
    from cbpos.core.services.theme_service import ThemeService

    # Inject stylesheet handler so ThemeService doesn't need PyQt imports
    ThemeService.set_stylesheet_handler(lambda css: app.setStyleSheet(css))
    saved_theme = ConfigService.get("theme")  # Returns "Dark" by default
    ThemeService.apply_theme(saved_theme)

    # Set application language from saved config
    from cbpos.i18n import register_language_callback, set_language

    saved_language = ConfigService.get("language") or "en"
    set_language(saved_language)

    # Re-apply theme on language changes so font-family prioritizes the active script (#589)
    register_language_callback(lambda: ThemeService.apply_theme(ThemeService.current_theme))

    # Never run on an out-of-date schema -- a failed migration must block startup (#630).
    if migration_error:
        from PyQt6.QtWidgets import QMessageBox

        from cbpos.i18n import _t

        QMessageBox.critical(
            None,
            _t("main_window.migration_failed_title"),
            _t("main_window.migration_failed_body", error=migration_error),
        )
        sys.exit(1)

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

    # Start scheduler timer for auto-report. Settings' save handler also
    # starts/stops this live when the checkbox changes (#320) -- this call
    # only covers the case where it was already enabled at launch.
    if ConfigService.get("auto_report_enabled"):
        try:
            from cbpos.core.services.scheduler_service import SchedulerService

            SchedulerService.start_timer()
            print("[BOOTSTRAP] Scheduler started.")
        except Exception as e:
            print(f"[BOOTSTRAP] Scheduler failed to start: {e}")

    # Register the manager-override handler so the core permission helper
    # can prompt for override without importing UI components itself.
    from cbpos.core.utils.permission_helper import set_override_handler
    from cbpos.ui.dialogs.manager_override_dialog import ManagerOverrideDialog

    def _manager_override(permission_code: str, parent=None):
        dialog = ManagerOverrideDialog(permission_code, parent)
        if dialog.exec():
            return dialog.authorized_user
        return None

    set_override_handler(_manager_override)

    # Launch main window
    window = MainWindow()
    window.showMaximized()  # Industrial apps usually run full screen

    # --- Multi-Terminal LAN Sync ---
    terminal_mode = ConfigService.get("terminal_mode") or "standalone"
    shared_secret = ConfigService.get("sync_shared_secret") or ""

    if terminal_mode in ("main", "terminal") and not shared_secret:
        print(
            "[BOOTSTRAP] LAN Sync is configured but no Shared Secret is set "
            "(Settings > Network > LAN Sync) — refusing to start sync "
            "unauthenticated."
        )
        window.sync_status.set_mode(terminal_mode)
        from cbpos.i18n import _t

        window.sync_status.set_config_error(_t("sync_status.error_shared_secret_required"))

    elif terminal_mode == "main":
        print("[BOOTSTRAP] Starting sync server (Main PC mode)...")
        from cbpos.infrastructure.sync_server import SyncServer

        sync_port = int(ConfigService.get("sync_server_port") or 5555)
        sync_server = SyncServer(port=sync_port)
        sync_server.started_signal.connect(window.sync_status.set_server_address)
        sync_server.terminal_connected.connect(window.sync_status.on_terminal_connected)
        sync_server.sync_completed.connect(window.sync_status.on_sync_completed)
        sync_server.start()
        window._sync_server = sync_server
        window.sync_status.set_mode("main")
        print(f"[BOOTSTRAP] Sync server starting on port {sync_port}")

    elif terminal_mode == "terminal":
        main_pc_address = ConfigService.get("main_pc_address") or ""
        if main_pc_address:
            print(f"[BOOTSTRAP] Starting sync client (Terminal mode) -> {main_pc_address}")
            from cbpos.infrastructure.sync_client import SyncClient

            terminal_id = ConfigService.get("terminal_id") or "TERM-01"
            sync_interval = int(ConfigService.get("sync_interval_seconds") or 3)
            sync_client = SyncClient(terminal_id, main_pc_address, sync_interval, shared_secret)
            sync_client.status_changed.connect(window.sync_status.set_state)
            sync_client.sync_completed.connect(window.sync_status.on_client_sync_completed)
            sync_client.start()
            window._sync_client = sync_client
            window.sync_status.set_mode("terminal")
            window.sync_status.set_server_address(main_pc_address)
        else:
            print("[BOOTSTRAP] Terminal mode but no main_pc_address configured")
            window.sync_status.set_mode("terminal")
            from cbpos.i18n import _t

            window.sync_status.set_config_error(_t("sync_status.error_main_pc_address_required"))
    else:
        window.sync_status.set_mode("standalone")

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
        _report_crash(*sys.exc_info())
        sys.exit(1)
