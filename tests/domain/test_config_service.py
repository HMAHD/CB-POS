"""Tests for ConfigService configuration and first-run detection (#791)."""

import json
import os

import pytest

from cbpos.core.services.config_service import ConfigService


@pytest.fixture
def isolated_config(tmp_path):
    """Point ConfigService at a throwaway settings file; restore afterwards."""
    original_file = ConfigService.SETTINGS_FILE
    original_settings = ConfigService._settings
    ConfigService.SETTINGS_FILE = os.path.join(tmp_path, "settings.json")
    ConfigService._settings = {}
    yield ConfigService.SETTINGS_FILE
    ConfigService.SETTINGS_FILE = original_file
    ConfigService._settings = original_settings


def test_issue_791_new_settings_file_is_not_setup_completed(isolated_config):
    """A fresh install without settings.json initializes setup_completed to False."""
    assert not os.path.exists(isolated_config)
    ConfigService.load()
    assert ConfigService.get("setup_completed") is False
    with open(isolated_config, encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("setup_completed") is False


def test_issue_791_legacy_settings_file_is_setup_completed(isolated_config):
    """An existing settings file lacking setup_completed is upgraded to True."""
    with open(isolated_config, "w", encoding="utf-8") as f:
        json.dump({"shop_name": "Legacy Shop", "theme": "Light"}, f)

    ConfigService.load()
    assert ConfigService.get("setup_completed") is True
    with open(isolated_config, encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("setup_completed") is True


def test_issue_838_zero_byte_settings_quarantined_and_bak_used(isolated_config, tmp_path):
    """A 0-byte settings.json is quarantined to .corrupt-* and restored from .bak."""
    # 1. Establish a good settings file and save it to produce settings.json.bak
    ConfigService.load()
    ConfigService.set("shop_name", "My Good Shop")
    bak_file = f"{isolated_config}.bak"
    assert os.path.exists(bak_file)

    # 2. Simulate sudden power failure truncating settings.json to 0 bytes
    with open(isolated_config, "w"):
        pass
    assert os.path.getsize(isolated_config) == 0

    # 3. Reload ConfigService
    ConfigService._settings = {}
    ConfigService.load()

    # 4. Values should come from .bak
    assert ConfigService.get("shop_name") == "My Good Shop"
    assert ConfigService.recovery_notice() == "restored_from_backup"

    # 5. Corrupt file was preserved
    corrupt_files = [f for f in os.listdir(tmp_path) if f.startswith("settings.json.corrupt-")]
    assert len(corrupt_files) == 1
    assert os.path.getsize(tmp_path / corrupt_files[0]) == 0


def test_issue_838_garbage_settings_without_bak_keeps_corrupt_copy(isolated_config, tmp_path):
    """Garbage settings without .bak drops to defaults, quarantines, and next save keeps corrupt file."""
    garbage_bytes = b"GARBAGE_NOT_JSON{{{\x00\xff"
    with open(isolated_config, "wb") as f:
        f.write(garbage_bytes)

    ConfigService._settings = {}
    ConfigService._loaded_from_defaults_after_failure = False
    ConfigService.load()

    assert ConfigService._loaded_from_defaults_after_failure is True
    assert ConfigService.recovery_notice() == "defaults_after_corruption"

    corrupt_files = [f for f in os.listdir(tmp_path) if f.startswith("settings.json.corrupt-")]
    assert len(corrupt_files) == 1
    with open(tmp_path / corrupt_files[0], "rb") as f:
        assert f.read() == garbage_bytes

    # Subsequent change saves defaults, but .bak must NOT be written from defaults-after-failure
    ConfigService.set("sidebar_collapsed", True)

    bak_file = f"{isolated_config}.bak"
    assert not os.path.exists(bak_file)

    # Corrupt copy is still intact
    with open(tmp_path / corrupt_files[0], "rb") as f:
        assert f.read() == garbage_bytes


def test_issue_838_write_fsyncs_before_replace(tmp_path, monkeypatch):
    """_write_restricted calls fsync before os.replace."""
    call_log = []
    real_fsync = os.fsync
    real_replace = os.replace

    def spy_fsync(fd):
        call_log.append("fsync")
        real_fsync(fd)

    def spy_replace(src, dst):
        call_log.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "replace", spy_replace)

    target_path = str(tmp_path / "test_write.json")
    ConfigService._write_restricted(target_path, '{"test": 1}')

    assert "fsync" in call_log
    assert "replace" in call_log
    fsync_idx = call_log.index("fsync")
    replace_idx = call_log.index("replace")
    assert fsync_idx < replace_idx


def test_issue_838_main_window_checks_recovery_notice(monkeypatch):
    """MainWindow._check_config_recovery_notices shows QMessageBox.warning once."""
    from unittest.mock import MagicMock

    from cbpos.ui.main_window import MainWindow

    warnings = []
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QMessageBox.warning",
        lambda parent, title, body: warnings.append((title, body)),
    )

    # 1. When recovery_notice() is 'restored_from_backup'
    ConfigService._recovery_reason = "restored_from_backup"
    win = MagicMock(spec=MainWindow)
    MainWindow._check_config_recovery_notices(win)

    assert len(warnings) == 1
    assert "Settings Recovery" in warnings[0][0]
    assert "loaded the last good copy" in warnings[0][1]

    # Notice was cleared (one-time notice)
    assert ConfigService.recovery_notice() is None
    MainWindow._check_config_recovery_notices(win)
    assert len(warnings) == 1  # No new warning shown

    # 2. When recovery_notice() is 'defaults_after_corruption'
    ConfigService._recovery_reason = "defaults_after_corruption"
    ConfigService._corrupt_filename = "settings.json.corrupt-20261030-120000"
    MainWindow._check_config_recovery_notices(win)

    assert len(warnings) == 2
    assert "Settings Recovery" in warnings[1][0]
    assert "settings.json.corrupt-20261030-120000" in warnings[1][1]
