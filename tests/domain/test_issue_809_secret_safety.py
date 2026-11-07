"""Tests for Issue #809: Random encryption key generation, DPAPI protection, and legacy migration."""

import base64
import hashlib
import json
import logging
import os
import platform

import pytest
from cryptography.fernet import Fernet, InvalidToken

from cbpos.core.services.config_service import ConfigService


def _derive_expected_legacy_hostname_key() -> bytes:
    seed = f"cbpos-{platform.node()}-{platform.system()}".encode()
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


@pytest.fixture
def clean_config(tmp_path, monkeypatch):
    """Isolate ConfigService in tmp_path with fresh state."""
    settings_file = str(tmp_path / "settings.json")
    key_file = str(tmp_path / ".encryption_key")
    backup_pw_file = str(tmp_path / ".backup_password")

    monkeypatch.setattr(ConfigService, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(ConfigService, "_KEY_FILE", key_file)
    monkeypatch.setattr(ConfigService, "_BACKUP_PASSWORD_FILE", backup_pw_file)
    monkeypatch.setattr(ConfigService, "_fernet", None)
    monkeypatch.setattr(ConfigService, "_settings", {})
    monkeypatch.setattr(ConfigService, "_frozen", False)
    ConfigService._undecryptable_keys.clear()

    yield {
        "dir": tmp_path,
        "settings": settings_file,
        "key": key_file,
        "backup_pw": backup_pw_file,
    }

    ConfigService._fernet = None
    ConfigService._settings = {}
    ConfigService._undecryptable_keys.clear()


def test_issue_809_new_install_generates_random_key(clean_config, tmp_path, monkeypatch):
    """Fresh installs generate cryptographically random keys with raw: or dpapi: prefix, never hostname."""
    legacy_key = _derive_expected_legacy_hostname_key()

    # Run install 1
    ConfigService.load()
    key_file_1 = clean_config["key"]
    assert os.path.exists(key_file_1)
    with open(key_file_1, encoding="ascii") as f:
        content_1 = f.read().strip()

    assert content_1.startswith(("raw:", "dpapi:"))
    if content_1.startswith("raw:"):
        key_bytes_1 = content_1[4:].encode("ascii")
    else:
        key_bytes_1 = content_1.encode("ascii")

    assert key_bytes_1 != legacy_key

    # Run install 2 in a separate directory
    tmp_path_2 = tmp_path / "inst2"
    tmp_path_2.mkdir()
    key_file_2 = str(tmp_path_2 / ".encryption_key")
    settings_file_2 = str(tmp_path_2 / "settings.json")
    monkeypatch.setattr(ConfigService, "SETTINGS_FILE", settings_file_2)
    monkeypatch.setattr(ConfigService, "_KEY_FILE", key_file_2)
    monkeypatch.setattr(ConfigService, "_fernet", None)
    monkeypatch.setattr(ConfigService, "_settings", {})

    ConfigService.load()
    assert os.path.exists(key_file_2)
    with open(key_file_2, encoding="ascii") as f:
        content_2 = f.read().strip()

    assert content_2.startswith(("raw:", "dpapi:"))
    assert content_1 != content_2


def test_issue_809_legacy_key_migrated_and_values_preserved(clean_config):
    """Settings and backup password encrypted with legacy hostname key are migrated to random key."""
    legacy_key = _derive_expected_legacy_hostname_key()
    legacy_fernet = Fernet(legacy_key)

    # Prepare settings encrypted with legacy key
    encrypted_secret = legacy_fernet.encrypt(b"SuperSecretDBPassword123").decode("ascii")
    encrypted_smtp = legacy_fernet.encrypt(b"MySmtpPassword").decode("ascii")

    initial_settings = {
        "shop_name": "Ceylon Retail Shop",
        "network_db_password": encrypted_secret,
        "smtp_pass": encrypted_smtp,
    }
    with open(clean_config["settings"], "w", encoding="utf-8") as f:
        json.dump(initial_settings, f)

    # Prepare backup password encrypted with legacy key
    encrypted_backup_pw = legacy_fernet.encrypt(b"ShopBackupPass99").decode("ascii")
    with open(clean_config["backup_pw"], "w", encoding="ascii") as f:
        f.write(encrypted_backup_pw)

    # Legacy key file with NO prefix
    with open(clean_config["key"], "w", encoding="ascii") as f:
        f.write(legacy_key.decode("ascii"))

    # Load and trigger migration
    ConfigService.load()

    # 1. In-memory settings decrypted correctly
    assert ConfigService.get("network_db_password") == "SuperSecretDBPassword123"
    assert ConfigService.get("smtp_pass") == "MySmtpPassword"
    assert ConfigService.get("shop_name") == "Ceylon Retail Shop"
    assert ConfigService.get_backup_password() == "ShopBackupPass99"

    # 2. Key file updated and prefixed
    with open(clean_config["key"], encoding="ascii") as f:
        new_key_content = f.read().strip()
    assert new_key_content.startswith(("raw:", "dpapi:"))
    assert new_key_content != legacy_key.decode("ascii")

    # 3. On-disk settings.json now uses new random key (legacy key can no longer decrypt)
    with open(clean_config["settings"], encoding="utf-8") as f:
        disk_settings = json.load(f)

    new_cipher = disk_settings["network_db_password"]
    assert new_cipher != encrypted_secret
    with pytest.raises(InvalidToken):
        legacy_fernet.decrypt(new_cipher.encode("ascii"))

    # 4. On-disk backup password also re-encrypted
    with open(clean_config["backup_pw"], encoding="ascii") as f:
        disk_backup_pw = f.read().strip()
    assert disk_backup_pw != encrypted_backup_pw
    with pytest.raises(InvalidToken):
        legacy_fernet.decrypt(disk_backup_pw.encode("ascii"))


def test_issue_809_unprefixed_random_key_migrated_and_wrapped(clean_config):
    """An unprefixed key file that decrypts stored values is migrated and wrapped."""
    old_random_key = Fernet.generate_key()
    old_fernet = Fernet(old_random_key)

    encrypted_secret = old_fernet.encrypt(b"CustomSecretToken").decode("ascii")
    with open(clean_config["settings"], "w", encoding="utf-8") as f:
        json.dump({"shop_name": "Old Key Shop", "sync_shared_secret": encrypted_secret}, f)

    with open(clean_config["key"], "w", encoding="ascii") as f:
        f.write(old_random_key.decode("ascii"))

    ConfigService.load()

    assert ConfigService.get("sync_shared_secret") == "CustomSecretToken"
    with open(clean_config["key"], encoding="ascii") as f:
        wrapped_key = f.read().strip()
    assert wrapped_key.startswith(("raw:", "dpapi:"))


def test_issue_809_dpapi_unwrap_failure_goes_to_reentry(clean_config, monkeypatch):
    """DPAPI unwrap failure quarantines the unreadable key, generates new random key, and marks secrets for reentry."""
    # Write a broken DPAPI key
    with open(clean_config["key"], "w", encoding="ascii") as f:
        f.write("dpapi:AAAA_INVALID_BLOB_FOR_OTHER_USER")

    # Save a setting that has a secret
    with open(clean_config["settings"], "w", encoding="utf-8") as f:
        json.dump(
            {
                "shop_name": "Preserved Shop",
                "smtp_pass": "gAAAAABl-sample-foreign-ciphertext",
            },
            f,
        )

    # Force unwrap to fail (simulating pywintypes.error / cross-user / corruption)
    if platform.system() == "Windows":
        import win32crypt

        def fail_unprotect(*args, **kwargs):
            raise OSError("Access denied by DPAPI")

        monkeypatch.setattr(win32crypt, "CryptUnprotectData", fail_unprotect)

    ConfigService.load()

    # Shop name preserved
    assert ConfigService.get("shop_name") == "Preserved Shop"
    # Secret marked for reentry
    assert ConfigService.get("smtp_pass") == ""
    assert "smtp_pass" in ConfigService.secrets_needing_reentry()

    # Old key was quarantined, new key generated
    corrupt_keys = [f for f in os.listdir(clean_config["dir"]) if f.startswith(".encryption_key.corrupt-")]
    assert len(corrupt_keys) == 1

    with open(clean_config["key"], encoding="ascii") as f:
        new_key = f.read().strip()
    assert new_key.startswith(("raw:", "dpapi:"))
    assert "AAAA_INVALID_BLOB" not in new_key


def test_issue_809_no_secrets_in_logs(clean_config, caplog):
    """Migration logs 'Settings encryption key upgraded' with zero secrets or key material."""
    legacy_key = _derive_expected_legacy_hostname_key()
    legacy_fernet = Fernet(legacy_key)

    secret_val = "P@ssw0rd_Very_Secret_987!"
    encrypted_secret = legacy_fernet.encrypt(secret_val.encode("utf-8")).decode("ascii")

    with open(clean_config["settings"], "w", encoding="utf-8") as f:
        json.dump({"network_db_password": encrypted_secret}, f)

    with open(clean_config["key"], "w", encoding="ascii") as f:
        f.write(legacy_key.decode("ascii"))

    with caplog.at_level(logging.DEBUG):
        ConfigService.load()

    all_logs = caplog.text
    assert "Settings encryption key upgraded" in all_logs
    assert secret_val not in all_logs
    assert legacy_key.decode("ascii") not in all_logs
