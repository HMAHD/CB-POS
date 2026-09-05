"""
Tests for SyncClient's Main PC identity pinning.

Terminal mode has no discovery/election protocol, so nothing stops a
second machine from being configured as "Main PC" at the same address.
These tests cover the guard against that: a Terminal pins whichever
instance_id it first connects with, and refuses to treat a later,
different instance_id as the same trusted Main PC.
"""

import os

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.sync_client import SyncClient


@pytest.fixture
def isolated_config(tmp_path):
    """Redirect ConfigService to a throwaway settings file for this test,
    restoring the real state afterward."""
    original_file = ConfigService.SETTINGS_FILE
    original_settings = ConfigService._settings
    ConfigService.SETTINGS_FILE = os.path.join(tmp_path, "settings.json")
    ConfigService._settings = {}
    ConfigService.load()
    yield
    ConfigService.SETTINGS_FILE = original_file
    ConfigService._settings = original_settings


@pytest.fixture
def client(isolated_config):
    return SyncClient("TERM-TEST", "127.0.0.1:9999", shared_secret="x")


class TestMainIdentityPinning:
    def test_first_connection_pins_the_identity(self, client):
        assert client._check_main_identity("abc123") is True
        assert ConfigService.get("sync_known_main_instance_id") == "abc123"

    def test_matching_identity_on_later_connections_passes(self, client):
        client._check_main_identity("abc123")
        assert client._check_main_identity("abc123") is True

    def test_different_identity_is_refused(self, client):
        client._check_main_identity("abc123")
        assert client._check_main_identity("xyz999") is False
        # And the pinned value must not have been silently overwritten.
        assert ConfigService.get("sync_known_main_instance_id") == "abc123"

    def test_missing_instance_id_does_not_break_older_servers(self, client):
        assert client._check_main_identity(None) is True
        assert client._check_main_identity("") is True

    def test_forgetting_the_main_pc_allows_a_new_identity(self, client):
        client._check_main_identity("abc123")
        assert client._check_main_identity("xyz999") is False

        # Simulate the "Forget Trusted Main PC" button.
        ConfigService.set("sync_known_main_instance_id", "")

        assert client._check_main_identity("xyz999") is True
        assert ConfigService.get("sync_known_main_instance_id") == "xyz999"
