"""Window icon and Windows taskbar identity for CB POS (#692).

The ``icon=`` in ``cbpos.spec`` only stamps the .exe file. Qt windows need
their own icon, and Windows groups taskbar buttons by AppUserModelID, so
without an explicit one the taskbar falls back to the generic python icon.
"""

import logging
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from cbpos.config import Config

logger = logging.getLogger(__name__)

APP_USER_MODEL_ID = "CeyByte.CBPOS"

_ICO_DIR = Path("cbpos") / "assets" / "ico"


def app_icon_path() -> Path:
    """Return the multi-size .ico bundled with the app (dev and frozen builds).

    Returns:
        Path: Absolute path to ``cbpos_multi.ico``.
    """
    return Config.BASE_DIR / _ICO_DIR / "cbpos_multi.ico"


def load_app_icon() -> QIcon:
    """Load the CB POS icon, falling back to the PNG if the .ico can't be read.

    Returns:
        QIcon: The application icon (null only if both files are missing).
    """
    icon = QIcon(str(app_icon_path()))
    if icon.isNull():
        icon = QIcon(str(Config.BASE_DIR / _ICO_DIR / "cbpos.png"))
    if icon.isNull():
        logger.warning("CB POS window icon not found under %s", Config.BASE_DIR / _ICO_DIR)
    return icon


def apply_app_icon(app: QApplication) -> QIcon:
    """Set the icon every window and dialog inherits.

    Args:
        app: The running QApplication.

    Returns:
        QIcon: The icon that was applied.
    """
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    return icon


def set_windows_app_user_model_id() -> bool:
    """Give the process its own taskbar identity so Windows shows the CB POS icon.

    Must run before the first window is created. A no-op on other platforms.

    Returns:
        bool: True if the ID was set.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        return True
    except (AttributeError, OSError) as e:
        logger.warning("Could not set AppUserModelID: %s", e)
        return False
