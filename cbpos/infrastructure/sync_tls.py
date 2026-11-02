"""TLS certificate management for CB-POS Multi-Terminal LAN Sync (#800).

The Main PC generates a self-signed certificate on first use and serves
HTTPS with it. Terminals connect over TLS and pin the Main PC's certificate
using VERIFY_X509_PARTIAL_CHAIN after mutual fingerprint confirmation by the user.
The TLS handshake rejects any unrecognized certificate before any HTTP request
bytes or shared-secret tokens are transmitted over the network.
"""

import contextlib
import hashlib
import logging
import os
import ssl
import stat
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from cbpos.config import Config

logger = logging.getLogger(__name__)

CERT_FILE = os.path.join(str(Config.DATA_DIR), "sync_tls_cert.pem")
KEY_FILE = os.path.join(str(Config.DATA_DIR), "sync_tls_key.pem")


class UnpairedError(Exception):
    """Raised when a Terminal attempts to connect or sync without a pinned certificate."""


def _write_restricted(path: str, data: bytes) -> None:
    """Write *data* to *path* with owner-only permissions (0600)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    with contextlib.suppress(OSError):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def get_or_create_certificate() -> tuple[str, str]:
    """Return (cert_path, key_path) for the Main PC's sync server,
    generating a self-signed certificate on first call. Safe to call on
    every startup — a fast no-op once the files exist.
    """
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return CERT_FILE, KEY_FILE

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CB POS LAN Sync")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("*")]), critical=False)
        .sign(key, hashes.SHA256())
    )

    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    _write_restricted(KEY_FILE, key_pem)
    _write_restricted(CERT_FILE, cert_pem)
    logger.info("Generated self-signed TLS certificate for LAN sync at %s", CERT_FILE)
    return CERT_FILE, KEY_FILE


def cert_fingerprint(pem: str, multiline: bool = False) -> str:
    """Calculate the SHA-256 fingerprint of an X.509 certificate in PEM format.

    Args:
        pem: Certificate PEM string.
        multiline: If True, returns 4 lines of 8 colon-separated hex pairs.
                   If False, returns all 32 colon-separated hex pairs on one line.

    Returns:
        Uppercase hex fingerprint string.
    """
    cert_bytes = pem.encode("ascii") if isinstance(pem, str) else pem
    cert = x509.load_pem_x509_certificate(cert_bytes)
    der = cert.public_bytes(serialization.Encoding.DER)
    digest = hashlib.sha256(der).hexdigest().upper()
    pairs = [digest[i : i + 2] for i in range(0, len(digest), 2)]
    if multiline:
        lines = [":".join(pairs[i : i + 8]) for i in range(0, len(pairs), 8)]
        return "\n".join(lines)
    return ":".join(pairs)


def fetch_server_certificate(host: str, port: int, timeout: float = 5.0) -> str:
    """Fetch the server's TLS certificate without sending any HTTP request or auth token.

    Args:
        host: Hostname or IP address of the Main PC.
        port: TLS port of the sync server.
        timeout: Network timeout in seconds.

    Returns:
        PEM-encoded certificate string.
    """
    return ssl.get_server_certificate((host, port), timeout=timeout)


def build_server_ssl_context() -> ssl.SSLContext:
    """Return an SSLContext for the Main PC's sync server."""
    cert_path, key_path = get_or_create_certificate()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context


def build_client_ssl_context(pinned_pem: str | None = None) -> ssl.SSLContext:
    """Return an SSLContext for a Terminal's sync client.

    Requires a pinned certificate PEM string. Uses VERIFY_X509_PARTIAL_CHAIN
    so the self-signed leaf certificate acts as its own trust anchor.
    Any mismatch causes the TLS handshake to fail before any HTTP bytes
    or shared secrets are sent.

    Raises:
        UnpairedError: If pinned_pem is None or empty.
    """
    if not pinned_pem:
        raise UnpairedError("Terminal is not paired with Main PC: no certificate pinned")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cadata=pinned_pem)
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return context
