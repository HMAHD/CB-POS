"""
TLS certificate management for CB-POS Multi-Terminal LAN Sync.

The Main PC generates a self-signed certificate on first use and serves
HTTPS with it. Terminals connect over TLS but cannot validate the
certificate against a CA — there isn't one, by design, for a LAN
appliance with no internet-facing identity to prove. This still
encrypts the wire against passive eavesdropping (packet sniffing on
shared Wi-Fi, a rogue device on the same switch) — it does not protect
against an active man-in-the-middle presenting a different
certificate. The shared-secret token every request already carries
(see sync_server.py/sync_client.py) covers that residual gap: a MITM
without the secret can observe encrypted traffic but can't forge a
request the server will accept. Closing it fully would need
certificate pinning with a confirm-fingerprint step on first connect,
which is a larger UX addition left for later.
"""

import logging
import os
import stat
import ssl
from datetime import datetime, timedelta, timezone
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from cbpos.config import Config

logger = logging.getLogger(__name__)

CERT_FILE = os.path.join(str(Config.DATA_DIR), "sync_tls_cert.pem")
KEY_FILE = os.path.join(str(Config.DATA_DIR), "sync_tls_key.pem")


def _write_restricted(path: str, data: bytes) -> None:
    """Write *data* to *path* with owner-only permissions (0600)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def get_or_create_certificate() -> Tuple[str, str]:
    """Return (cert_path, key_path) for the Main PC's sync server,
    generating a self-signed certificate on first call. Safe to call on
    every startup — a fast no-op once the files exist."""
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return CERT_FILE, KEY_FILE

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CB POS LAN Sync")])
    now = datetime.now(timezone.utc)
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


def build_server_ssl_context() -> ssl.SSLContext:
    """Return an SSLContext for the Main PC's sync server."""
    cert_path, key_path = get_or_create_certificate()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context


def build_client_ssl_context() -> ssl.SSLContext:
    """Return an SSLContext for a Terminal's sync client.

    Certificate verification is disabled — see module docstring for why.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context
