"""#618: sizes used to be shown as f"{size_mb:.1f} MB", so every real
44 KB backup read "0.0 MB" and owners concluded their backups were empty.
"""

import pytest

from cbpos.core.services.backup_service import BackupService
from cbpos.core.utils.formatters import format_bytes
from tests.unit.backup_helpers import data_dir, make_pos_db


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0 KB"),
        (1, "1 KB"),
        (44 * 1024, "44 KB"),
        (45_000, "44 KB"),
        (540 * 1024, "540 KB"),
        (1024 * 1024 - 100, "1.0 MB"),
        (1024 * 1024, "1.0 MB"),
        (int(1.3 * 1024 * 1024), "1.3 MB"),
        (250 * 1024 * 1024, "250.0 MB"),
        (5 * 1024**3, "5.0 GB"),
        (-2048, "-2 KB"),
    ],
)
def test_format_bytes(size, expected):
    assert format_bytes(size) == expected


def test_list_backups_shows_real_and_original_sizes(tmp_path):
    make_pos_db(tmp_path / "cbpos.db")
    with data_dir(tmp_path):
        path = BackupService.create_backup(str(tmp_path / "backups"), "shop-secret-42")

    (backup,) = BackupService.list_backups(str(tmp_path / "backups"))

    assert backup["path"] == path
    assert backup["size"] != "0.0 MB"
    assert backup["size"].endswith(" KB")
    assert backup["original_size"].endswith(" KB")
