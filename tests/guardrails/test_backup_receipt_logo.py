"""
#626: the receipt logo (DATA_DIR/assets) is backed up and restored.

Settings store the logo as "assets/receipt_logo.<ext>", relative to the
data folder, so restoring a backup into a clean data folder -- e.g. on a
new PC -- must bring the file back too. Everything runs in tmp_path.
"""

import json

import pytest
import pyzipper
from PIL import Image

from cbpos.core.services.backup_service import BackupService
from cbpos.core.services.config_service import ConfigService
from tests.helpers.backup_helpers import data_dir, isolate_config_service, make_pos_db

SHOP_PASSWORD = "shop-secret-42"


@pytest.fixture
def env(tmp_path, monkeypatch):
    isolate_config_service(monkeypatch, tmp_path)
    ConfigService.set_backup_password(SHOP_PASSWORD)
    make_pos_db(tmp_path / "cbpos.db")
    (tmp_path / "settings.json").write_text(json.dumps({"receipt_logo_path": "assets/receipt_logo.png"}))
    (tmp_path / "assets").mkdir()
    Image.new("RGB", (50, 20), "black").save(tmp_path / "assets" / "receipt_logo.png")
    return tmp_path


def _backup(env) -> str:
    with data_dir(env):
        return BackupService.create_backup(str(env / "backups"), SHOP_PASSWORD)


def test_backup_contains_the_logo(env):
    backup = _backup(env)

    with pyzipper.AESZipFile(backup) as zf:
        zf.setpassword(SHOP_PASSWORD.encode())
        assert "assets/receipt_logo.png" in zf.namelist()
        assert zf.read("assets/receipt_logo.png") == (env / "assets" / "receipt_logo.png").read_bytes()


def test_restore_puts_the_logo_back_in_a_clean_data_folder(env):
    backup = _backup(env)
    logo_bytes = (env / "assets" / "receipt_logo.png").read_bytes()
    (env / "assets" / "receipt_logo.png").unlink()
    (env / "assets").rmdir()
    (env / "settings.json").unlink()

    with data_dir(env):
        BackupService.restore_backup(backup, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

    assert (env / "assets" / "receipt_logo.png").read_bytes() == logo_bytes
    assert json.loads((env / "settings.json").read_text())["receipt_logo_path"] == "assets/receipt_logo.png"


def test_restored_logo_replaces_a_logo_with_another_extension(env):
    backup = _backup(env)
    (env / "assets" / "receipt_logo.png").unlink()
    Image.new("RGB", (10, 10), "white").save(env / "assets" / "receipt_logo.jpg")

    with data_dir(env):
        BackupService.restore_backup(backup, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

    assert sorted(p.name for p in (env / "assets").iterdir()) == ["receipt_logo.png"]


def test_backup_without_assets_leaves_current_logo(env):
    (env / "assets" / "receipt_logo.png").rename(env / "keep.png")
    (env / "assets").rmdir()
    backup = _backup(env)  # made before the shop had a logo
    (env / "assets").mkdir()
    (env / "keep.png").rename(env / "assets" / "receipt_logo.png")

    with data_dir(env):
        BackupService.restore_backup(backup, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

    assert (env / "assets" / "receipt_logo.png").exists()
