"""Path validation and safety utilities (#881, #900)."""

import os
from pathlib import Path

from cbpos.i18n import _t


def ensure_writable_target(path: str | Path) -> Path:
    """Validate that `path` is an absolute path whose parent folder exists and is writable (#881).

    Accepts any user-chosen destination (e.g. USB stick, network drive, external volume)
    as long as:
    1. The path is absolute (no relative paths).
    2. No path traversal (e.g. '..') is present.
    3. The parent directory exists.
    4. The parent directory is writable (os.W_OK).
    5. If the target file already exists, it is writable.

    Args:
        path: Destination file path.

    Returns:
        The resolved Path object.

    Raises:
        ValueError: If path is relative or contains path traversal.
        FileNotFoundError: If parent folder does not exist.
        PermissionError: If parent folder or existing file is not writable.
    """
    raw_p = Path(path)
    raw_str = str(path)
    if not raw_p.is_absolute():
        raise ValueError(f"Path must be absolute: {path}")

    if ".." in raw_p.parts or ".." in raw_str.split("/") or ".." in raw_str.split("\\"):
        raise ValueError(f"Path traversal detected: {path}")

    resolved = raw_p.resolve()
    if ".." in resolved.parts:
        raise ValueError(f"Path traversal detected: {path}")

    parent = resolved.parent

    if not parent.exists():
        err = FileNotFoundError(f"Folder does not exist: {parent}")
        err.filename = str(parent)
        raise err

    if not os.access(parent, os.W_OK):
        err = PermissionError(f"Folder is not writable: {parent}")
        err.filename = str(parent)
        raise err

    if resolved.exists() and not os.access(resolved, os.W_OK):
        err = PermissionError(f"File is not writable: {resolved}")
        err.filename = str(resolved)
        raise err

    return resolved


def format_export_error(error: Exception | str, filepath: str | Path | None = None) -> str:
    """Format an export error message for display to the user (#881)."""
    err_str = str(error)
    folder = ""
    if filepath:
        folder = str(Path(filepath).parent)
    elif getattr(error, "filename", None):
        folder = str(error.filename)
    elif "Folder is not writable:" in err_str:
        folder = err_str.split("Folder is not writable:", 1)[1].strip()
    elif "Folder does not exist:" in err_str:
        folder = err_str.split("Folder does not exist:", 1)[1].strip()

    if (
        isinstance(error, PermissionError)
        or "not writable" in err_str.lower()
        or "permission denied" in err_str.lower()
    ):
        folder_display = folder or "the selected folder"
        return _t(
            "export.not_writable",
            folder=folder_display,
            default=f"Can't save to {folder_display}. Check the USB drive is plugged in and not write-protected.",
        )
    return err_str
