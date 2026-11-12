import os
import platform
import sys
from pathlib import Path


class Config:
    """App-wide constants: version, theme colors, and the DB/data-directory paths
    resolved for the current environment (dev vs. installed, per-OS AppData).
    """

    APP_NAME = "CB POS"
    VERSION = "1.3.0"
    BUILD_DATE: str | None = None

    # Application code / assets directory (where the source lives).
    BASE_DIR = Path(__file__).parent.parent

    # ---------------------------------------------------------------------------
    # User data directory — stores database, settings, encryption key, logs,
    # and backups.  Kept OUTSIDE the install directory so that updates via
    # Inno Setup (or any installer) never touch user data.
    #
    # * Installed (PyInstaller frozen): platform-specific AppData
    # * Development (running from source): project root (unchanged behaviour)
    # ---------------------------------------------------------------------------
    if getattr(sys, "frozen", False):
        _system = platform.system()
        if _system == "Windows":
            DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CB POS"
        elif _system == "Darwin":
            DATA_DIR = Path.home() / "Library" / "Application Support" / "CB POS"
        else:  # Linux / other
            DATA_DIR = Path.home() / ".local" / "share" / "cbpos"
    else:
        # Running from source — keep everything in the project root.
        DATA_DIR = BASE_DIR

    DB_URI = f"sqlite:///{DATA_DIR / 'cbpos.db'}"

    # Theme Colors
    COLOR_NAVY = "#001F3F"
    COLOR_CYAN = "#00BCEB"
