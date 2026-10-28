"""#619: the shop backup password is stored encrypted with the app
encryption key, in its own file -- never in plaintext, never in
settings.json (which is copied into every backup and overwritten by
every restore).
"""

import json

import pytest
from cryptography.fernet import Fernet

from cbpos.core.services.config_service import ConfigService
from tests.helpers.backup_helpers import isolate_config_service

SHOP_PASSWORD = "shop-secret-42"


@pytest.fixture
def env(tmp_path, monkeypatch):
    isolate_config_service(monkeypatch, tmp_path)
    return tmp_path


class TestShopPasswordStorage:
    def test_not_set_by_default(self, env):
        assert ConfigService.get_backup_password() is None
        assert ConfigService.has_backup_password() is False

    def test_round_trips(self, env):
        ConfigService.set_backup_password(SHOP_PASSWORD)
        assert ConfigService.get_backup_password() == SHOP_PASSWORD
        assert ConfigService.has_backup_password() is True

    def test_never_stored_in_plaintext(self, env):
        ConfigService.set("shop_name", "Test Shop")  # make sure settings.json exists
        ConfigService.set_backup_password(SHOP_PASSWORD)

        for f in env.iterdir():
            if f.is_file():
                assert SHOP_PASSWORD.encode() not in f.read_bytes(), f.name
        settings = json.loads((env / "settings.json").read_text(encoding="utf-8"))
        assert SHOP_PASSWORD not in json.dumps(settings)

    def test_too_short_is_rejected(self, env):
        with pytest.raises(ValueError):
            ConfigService.set_backup_password("123")
        assert ConfigService.get_backup_password() is None

    def test_undecryptable_value_counts_as_not_set(self, env, monkeypatch):
        ConfigService.set_backup_password(SHOP_PASSWORD)
        # Simulate the password file ending up next to a different key.
        other_key = env / "other_key"
        other_key.write_bytes(Fernet.generate_key())
        monkeypatch.setattr(ConfigService, "_fernet", None)
        monkeypatch.setattr(ConfigService, "_KEY_FILE", str(other_key))

        assert ConfigService.get_backup_password() is None
