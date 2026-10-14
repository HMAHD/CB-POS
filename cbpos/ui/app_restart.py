"""Relaunch CB POS so settings that only apply at startup take effect (#581)."""

import logging
import os
import sys

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QApplication, QWidget

from cbpos.config import Config

logger = logging.getLogger(__name__)


def restart_command() -> tuple[str, list[str]]:
    """Return the program and arguments that start a fresh CB POS instance.

    Frozen (PyInstaller) builds relaunch the exe itself with no arguments;
    a source checkout relaunches the same interpreter on ``main.py``.

    Returns:
        tuple[str, list[str]]: ``(program, args)`` for ``QProcess.startDetached``.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, []
    return sys.executable, [str(Config.BASE_DIR / "main.py")]


def restart_application(window: QWidget) -> bool:
    """Close the app through its normal close path, then start a new instance.

    The window is closed first so its ``closeEvent`` (sync threads, print
    worker, auto-backup on close) finishes before the new instance opens
    the database. If the close is refused, nothing is relaunched.

    Args:
        window: The application's main window.

    Returns:
        bool: True if a new instance was started and this one is quitting.
    """
    if not window.close():
        return False

    watchdog = getattr(window, "watchdog", None)
    if watchdog is not None:
        watchdog.stop_monitoring()
    try:
        from cbpos.core.database import Database
        from cbpos.core.services.scheduler_service import SchedulerService

        SchedulerService.stop_timer()
        Database().engine.dispose()
    except Exception:
        logger.exception("Shutdown before restart was not fully clean")

    # Free the single-instance name and flag the child as our relaunch, so it
    # takes over instead of handing off to this exiting process (#691).
    from cbpos.infrastructure import single_instance

    single_instance.release()
    os.environ[single_instance.RESTART_ENV_VAR] = "1"

    program, args = restart_command()
    if getattr(sys, "frozen", False):
        # A one-file exe started by another one-file instance would otherwise
        # reuse the parent's temp unpack dir, which is deleted when we exit.
        os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    started = QProcess.startDetached(program, args)
    # PyQt6 returns (ok, pid) for the static overload
    ok = started[0] if isinstance(started, tuple) else bool(started)
    os.environ.pop(single_instance.RESTART_ENV_VAR, None)
    if not ok:
        logger.error("Could not relaunch CB POS (%s %s)", program, args)

    QApplication.quit()
    return ok
