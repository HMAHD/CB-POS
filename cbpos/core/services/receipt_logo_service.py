"""Keep the receipt logo inside the app's data folder (#626).

Settings used to store the path of whatever file the owner picked (e.g. a
file in Downloads). Moving or deleting that file, or restoring a backup on
another PC, silently dropped the logo from every receipt. The picked image
is now copied to ``DATA_DIR/assets/receipt_logo.<ext>`` and settings store
the path *relative* to the data folder, so it travels with backups and
works on any PC the data folder is restored to.
"""

import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from PIL import Image

from cbpos.config import Config

ASSETS_DIR_NAME = "assets"
LOGO_STEM = "receipt_logo"


def assets_dir() -> Path:
    """The data folder's assets directory (backed up with the database)."""
    return Path(Config.DATA_DIR) / ASSETS_DIR_NAME


def store_receipt_logo(source: str) -> str:
    """Copy the image at *source* in as the shop's receipt logo.

    Replaces any earlier ``receipt_logo.*`` so only one logo is kept.

    Args:
        source: The image file the owner picked.

    Returns:
        The path to save in settings: relative to the data folder,
        e.g. ``assets/receipt_logo.png``.

    Raises:
        ValueError: If *source* is not an image Pillow can read.
        OSError: If the file can't be read or copied.
    """
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"Logo file not found: {src}")
    try:
        with Image.open(src) as img:
            img.verify()
    except Exception as e:
        raise ValueError(f"Not a readable image: {src.name}") from e

    ext = src.suffix.lower() or ".png"
    target_dir = assets_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{LOGO_STEM}{ext}"

    if not (target.exists() and os.path.samefile(src, target)):
        fd, tmp = tempfile.mkstemp(dir=target_dir, prefix=f".{LOGO_STEM}.", suffix=".tmp")
        os.close(fd)
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    for old in target_dir.glob(f"{LOGO_STEM}.*"):
        if old != target:
            old.unlink(missing_ok=True)

    return str(PurePosixPath(ASSETS_DIR_NAME, target.name))


def resolve_receipt_logo(path: str | None) -> str:
    """Turn a stored logo path into a real file path ("" if none).

    Relative paths (the copied logo) are inside the data folder; absolute
    ones are left as they are, for settings saved before #626.
    """
    if not path:
        return ""
    p = Path(path)
    return str(p if p.is_absolute() else Path(Config.DATA_DIR) / p)
