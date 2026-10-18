"""Operating system integration helpers (calculator, external tools)."""

import logging
import platform
import shutil
import subprocess

logger = logging.getLogger(__name__)


def open_native_calculator() -> bool:
    """Launch the host operating system's native calculator.

    Supported platforms:
    - macOS (Darwin): /System/Applications/Calculator.app via ``open -a Calculator``
    - Windows: ``calc.exe``
    - Linux / Unix: search for gnome-calculator, kcalc, galculator, mate-calc, or xcalc

    Returns:
        bool: True if the process was successfully dispatched, False otherwise.
    """
    sys_name = platform.system()
    try:
        if sys_name == "Darwin":
            subprocess.Popen(["open", "-a", "Calculator"])
            return True
        elif sys_name == "Windows":
            subprocess.Popen(["calc.exe"], shell=True)
            return True
        else:  # Linux / Unix
            for candidate in ["gnome-calculator", "kcalc", "galculator", "mate-calc", "xcalc"]:
                if shutil.which(candidate):
                    subprocess.Popen([candidate])
                    return True
            # Fallback
            subprocess.Popen(["xcalc"])
            return True
    except Exception as exc:
        logger.exception("Failed to launch native calculator: %s", exc)
        return False
