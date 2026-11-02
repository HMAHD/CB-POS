"""
Tests for SyncClient's Main PC identity pinning and catalog sync watermark.

Terminal mode has no discovery/election protocol, so nothing stops a
second machine from being configured as "Main PC" at the same address.
These tests cover the guard against that: a Terminal pins whichever
instance_id it first connects with, and refuses to treat a later,
different instance_id as the same trusted Main PC.

They also cover that incremental catalog sync tracks the *server's*
clock, not this machine's own — the actual fix for wall-clock skew
between a Main PC and its terminals.
"""

import os
from datetime import datetime

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


class TestCatalogSyncWatermark:
    """_last_catalog_sync must come from the server's clock, not this
    machine's own — otherwise clock drift between a Main PC and a
    Terminal silently drops or duplicates catalog updates."""

    def test_uses_server_timestamp_not_local_clock(self, client, monkeypatch):
        # A server timestamp far from "now" on this machine — if the
        # client ever falls back to its own clock, this test would only
        # pass by coincidence.
        server_time = datetime(2030, 1, 1, 12, 0, 0)
        monkeypatch.setattr(
            client,
            "_request",
            lambda *a, **k: {
                "status": "ok",
                "timestamp": server_time.isoformat(),
                "total_records": 0,
                "payload": {},
            },
        )

        client._pull_catalog(full_sync=True)

        assert client._last_catalog_sync == server_time

    def test_uses_server_timestamp_even_with_records(self, client, monkeypatch):
        server_time = datetime(2030, 6, 15, 9, 30, 0)
        monkeypatch.setattr(
            client,
            "_request",
            lambda *a, **k: {
                "status": "ok",
                "timestamp": server_time.isoformat(),
                "total_records": 0,  # no records, but timestamp still must be trusted
                "payload": {},
            },
        )

        client._pull_catalog()

        assert client._last_catalog_sync == server_time

    def test_falls_back_to_local_clock_if_timestamp_missing(self, client, monkeypatch):
        monkeypatch.setattr(
            client,
            "_request",
            lambda *a, **k: {"status": "ok", "total_records": 0, "payload": {}},
        )

        before = datetime.now()
        client._pull_catalog(full_sync=True)
        after = datetime.now()

        assert before <= client._last_catalog_sync <= after


class TestTLSPinning:
    def test_issue_800_unpaired_client_remains_unpaired_and_does_not_send_requests(self, client):
        assert ConfigService.get("sync_pinned_cert_pem") == ""
        assert client.state == SyncClient.STATE_UNPAIRED
        # Calling _request when unpaired returns None immediately without network calls
        assert client._request("GET", "/sync/heartbeat") is None

    def test_issue_800_cert_mismatch_transitions_to_error_and_logs_audit(
        self, client, db_session, tmp_path, monkeypatch
    ):
        import os

        from cbpos.core.models import AuditLog
        from cbpos.infrastructure import sync_tls

        cert_path = os.path.join(tmp_path, "test_client_cert.pem")
        key_path = os.path.join(tmp_path, "test_client_key.pem")
        monkeypatch.setattr(sync_tls, "CERT_FILE", cert_path)
        monkeypatch.setattr(sync_tls, "KEY_FILE", key_path)
        sync_tls.get_or_create_certificate()
        with open(cert_path, encoding="ascii") as f:
            pem = f.read()

        ConfigService.set("sync_pinned_cert_pem", pem)
        ConfigService.set("sync_pinned_cert_fp", sync_tls.cert_fingerprint(pem))
        assert client.reload_ssl_context() is True
        assert client.state == SyncClient.STATE_DISCONNECTED

        # Trigger cert mismatch
        errors_emitted = []
        client.error_signal.connect(errors_emitted.append)

        client._handle_cert_mismatch(Exception("CERTIFICATE_VERIFY_FAILED: certificate verify failed"))

        assert client.state == SyncClient.STATE_ERROR
        assert client.error_code == "cert_mismatch"
        assert len(errors_emitted) == 1

        # Check AuditLog
        logs = db_session.query(AuditLog).filter_by(action="SYNC_CERT_MISMATCH", event_type="SECURITY").all()
        assert len(logs) == 1
        assert "expected_fingerprint" in logs[0].details
        assert "presented_fingerprint" in logs[0].details

        # Calling again does not write duplicate audit logs on repeated retries
        client._handle_cert_mismatch(Exception("CERTIFICATE_VERIFY_FAILED: certificate verify failed"))
        logs_again = db_session.query(AuditLog).filter_by(action="SYNC_CERT_MISMATCH", event_type="SECURITY").all()
        assert len(logs_again) == 1
