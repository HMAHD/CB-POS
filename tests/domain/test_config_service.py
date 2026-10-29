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
