"""
Simple backup service for end-of-day database and assets backup.
Full backup system will be implemented in Phase 17.
"""

import logging
import zipfile
from datetime import datetime
from pathlib import Path
from cbpos.config import Config

logger = logging.getLogger(__name__)


class BackupService:
    """Creates zip backups of the SQLite database and product images."""

    @staticmethod
    def create_backup(destination_dir: str) -> str:
        """
        Create a zip backup of the database file and product images.

        Args:
            destination_dir: Directory where backup zip will be saved.

        Returns:
            str: Path to the created backup file.

        Raises:
            FileNotFoundError: If database file doesn't exist.
            OSError: If backup directory can't be created.
        """
        dest = Path(destination_dir)
        dest.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"cbpos_backup_{timestamp}.zip"
        backup_path = dest / backup_name

        db_file = Config.BASE_DIR / "cbpos.db"
        images_dir = Config.BASE_DIR / "cbpos" / "assets" / "products"

        if not db_file.exists():
            raise FileNotFoundError(f"Database file not found: {db_file}")

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add database
            zf.write(db_file, "cbpos.db")
            logger.info(f"Added database to backup: {db_file}")

            # Add product images (if directory exists)
            if images_dir.exists():
                for img_file in images_dir.rglob("*"):
                    if img_file.is_file():
                        arcname = f"products/{img_file.relative_to(images_dir)}"
                        zf.write(img_file, arcname)

            # Add settings.json
            settings_file = Config.BASE_DIR / "settings.json"
            if settings_file.exists():
                zf.write(settings_file, "settings.json")

        logger.info(f"Backup created: {backup_path}")
        return str(backup_path)

    @staticmethod
    def get_default_backup_dir() -> str:
        """Return default backup directory (user's Documents/CB-POS-Backups)."""
        return str(Path.home() / "Documents" / "CB-POS-Backups")
