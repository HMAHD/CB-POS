"""
Tests for LAN Sync's TLS certificate management.

Covers the properties that matter for a self-signed, LAN-only
certificate: it gets generated once and reused (not regenerated on
every server start), it's written with owner-only permissions since
the private key lives alongside it, and the client/server SSL contexts
are configured for the "TLS for confidentiality, shared-secret for
authentication" trust model documented in sync_tls.py.
"""

import os
import ssl
import stat

import pytest

import cbpos.infrastructure.sync_tls as sync_tls


@pytest.fixture
def isolated_cert_paths(tmp_path, monkeypatch):
    """Redirect the module's cert/key file paths to a throwaway directory."""
    cert_path = os.path.join(tmp_path, "sync_tls_cert.pem")
    key_path = os.path.join(tmp_path, "sync_tls_key.pem")
    monkeypatch.setattr(sync_tls, "CERT_FILE", cert_path)
    monkeypatch.setattr(sync_tls, "KEY_FILE", key_path)
    return cert_path, key_path


class TestCertificateGeneration:
    def test_generates_cert_and_key_files(self, isolated_cert_paths):
        cert_path, key_path = isolated_cert_paths
        sync_tls.get_or_create_certificate()
        assert os.path.exists(cert_path)
        assert os.path.exists(key_path)

    def test_files_are_owner_only(self, isolated_cert_paths):
        cert_path, key_path = isolated_cert_paths
        sync_tls.get_or_create_certificate()
        for path in (cert_path, key_path):
            mode = stat.S_IMODE(os.stat(path).st_mode)
            assert mode == stat.S_IRUSR | stat.S_IWUSR, f"{path} is not owner-only (mode {oct(mode)})"

    def test_is_idempotent_across_calls(self, isolated_cert_paths):
        cert_path, _ = isolated_cert_paths
        sync_tls.get_or_create_certificate()
        with open(cert_path, "rb") as f:
            first = f.read()

        sync_tls.get_or_create_certificate()
        with open(cert_path, "rb") as f:
            second = f.read()

        assert first == second, "calling get_or_create_certificate() again regenerated the cert"

    def test_returns_the_configured_paths(self, isolated_cert_paths):
        cert_path, key_path = isolated_cert_paths
        returned_cert, returned_key = sync_tls.get_or_create_certificate()
        assert returned_cert == cert_path
        assert returned_key == key_path


class TestSSLContexts:
    def test_server_context_loads_the_certificate(self, isolated_cert_paths):
        context = sync_tls.build_server_ssl_context()
        assert isinstance(context, ssl.SSLContext)
        assert context.protocol == ssl.PROTOCOL_TLS_SERVER

    def test_client_context_does_not_verify(self, isolated_cert_paths):
        context = sync_tls.build_client_ssl_context()
        assert isinstance(context, ssl.SSLContext)
        assert context.check_hostname is False
        assert context.verify_mode == ssl.CERT_NONE
