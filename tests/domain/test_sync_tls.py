"""Tests for LAN Sync's TLS certificate management and pinning (#800)."""

import http.server
import os
import ssl
import stat
import threading
import urllib.error
import urllib.request

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


class TestFingerprint:
    def test_issue_800_fingerprint_format(self, isolated_cert_paths):
        cert_path, _ = sync_tls.get_or_create_certificate()
        with open(cert_path, encoding="ascii") as f:
            pem = f.read()

        # Canonical format: 32 hex pairs separated by colons (32*2 + 31 = 95 chars)
        fp = sync_tls.cert_fingerprint(pem)
        assert len(fp) == 95
        pairs = fp.split(":")
        assert len(pairs) == 32
        for pair in pairs:
            assert len(pair) == 2
            int(pair, 16)  # valid hex
            assert pair == pair.upper()

        # Multiline format: 4 lines of 8 pairs
        multi = sync_tls.cert_fingerprint(pem, multiline=True)
        lines = multi.split("\n")
        assert len(lines) == 4
        for line in lines:
            line_pairs = line.split(":")
            assert len(line_pairs) == 8


class TestSSLContexts:
    def test_server_context_loads_the_certificate(self, isolated_cert_paths):
        context = sync_tls.build_server_ssl_context()
        assert isinstance(context, ssl.SSLContext)
        assert context.protocol == ssl.PROTOCOL_TLS_SERVER

    def test_issue_800_unpaired_client_does_not_sync(self):
        with pytest.raises(sync_tls.UnpairedError):
            sync_tls.build_client_ssl_context(None)

        with pytest.raises(sync_tls.UnpairedError):
            sync_tls.build_client_ssl_context("")

    def test_issue_800_pinned_context_accepts_pinned_cert_and_rejects_other(self, tmp_path, monkeypatch):
        """Verify that pinned context accepts matching cert and rejects mismatch before any request bytes."""
        # 1. Generate cert A
        cert_a_path = os.path.join(tmp_path, "cert_a.pem")
        key_a_path = os.path.join(tmp_path, "key_a.pem")
        monkeypatch.setattr(sync_tls, "CERT_FILE", cert_a_path)
        monkeypatch.setattr(sync_tls, "KEY_FILE", key_a_path)
        sync_tls.get_or_create_certificate()
        with open(cert_a_path, encoding="ascii") as f:
            pem_a = f.read()

        # 2. Generate cert B (different)
        cert_b_path = os.path.join(tmp_path, "cert_b.pem")
        key_b_path = os.path.join(tmp_path, "key_b.pem")
        monkeypatch.setattr(sync_tls, "CERT_FILE", cert_b_path)
        monkeypatch.setattr(sync_tls, "KEY_FILE", key_b_path)
        sync_tls.get_or_create_certificate()
        with open(cert_b_path, encoding="ascii") as f:
            pem_b = f.read()

        assert pem_a != pem_b

        # Handler that tracks requests received
        requests_received = []

        class SimpleHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests_received.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")

            def log_message(self, *args):
                pass

        # Start HTTPS server with cert A
        server_ctx_a = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx_a.load_cert_chain(cert_a_path, key_a_path)

        httpd = http.server.HTTPServer(("127.0.0.1", 0), SimpleHandler)
        httpd.socket = server_ctx_a.wrap_socket(httpd.socket, server_side=True)
        port = httpd.server_address[1]

        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        try:
            # Test fetch_server_certificate retrieves cert A without error
            fetched_pem = sync_tls.fetch_server_certificate("127.0.0.1", port)
            assert sync_tls.cert_fingerprint(fetched_pem) == sync_tls.cert_fingerprint(pem_a)
            # Fetching certificate does not send an HTTP request
            assert len(requests_received) == 0

            # Client pinned to cert A succeeds
            client_ctx_a = sync_tls.build_client_ssl_context(pem_a)
            req = urllib.request.Request(f"https://127.0.0.1:{port}/test")
            with urllib.request.urlopen(req, context=client_ctx_a, timeout=5) as resp:
                assert resp.read() == b"OK"
            assert len(requests_received) == 1

            # Client pinned to cert B is rejected during TLS handshake
            client_ctx_b = sync_tls.build_client_ssl_context(pem_b)
            req_rejected = urllib.request.Request(f"https://127.0.0.1:{port}/test_rejected")
            with pytest.raises((urllib.error.URLError, ssl.SSLCertVerificationError)) as exc_info:
                urllib.request.urlopen(req_rejected, context=client_ctx_b, timeout=5)

            # Ensure error is an SSL verification error
            err_str = str(exc_info.value)
            assert "CERTIFICATE_VERIFY_FAILED" in err_str or "certificate verify failed" in err_str.lower()

            # The server saw NO second request because TLS handshake was aborted!
            assert len(requests_received) == 1

        finally:
            httpd.shutdown()
            httpd.server_close()
