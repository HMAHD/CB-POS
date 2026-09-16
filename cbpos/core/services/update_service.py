"""Auto-update service for CB POS.

Checks the public releases repository for a newer version and downloads
the installer when the user requests an update.

Update manifest (``latest.json``) is hosted at:
    https://raw.githubusercontent.com/ceybyte/cbpos-releases/main/latest.json

The manifest schema::

    {
        "version": "1.1.0",
        "release_date": "2026-03-15",
        "download_url": "https://github.com/ceybyte/cbpos-releases/releases/download/v1.1.0/CBPOSSetup-1.1.0.exe",
        "changelog": "Bug fixes and new reporting features.",
        "min_version": "1.0.0",
        "sha256": "abc123..."
    }
"""

import hashlib
import json
import logging
import os
import tempfile
import urllib.error
import urllib.request
from typing import Any

from packaging.version import InvalidVersion, Version

from cbpos.config import Config

logger = logging.getLogger(__name__)

_MANIFEST_URL = "https://raw.githubusercontent.com/ceybyte/cbpos-releases/main/latest.json"

# Timeout for network requests (seconds).
_TIMEOUT = 15


def _safe_version(v: str) -> Version | None:
    """Parse a PEP 440 version string, returning None on failure."""
    try:
        return Version(v.strip())
    except (InvalidVersion, AttributeError):
        return None


class UpdateService:
    """Check for and download application updates."""

    @staticmethod
    def check_for_update() -> dict[str, Any] | None:
        """Check the remote manifest for a newer version.

        Returns:
            A dict with the manifest data if a newer version is available,
            or ``None`` if the app is up-to-date or the check fails.
        """
        try:
            req = urllib.request.Request(_MANIFEST_URL, headers={"User-Agent": "CBPOS-Updater"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            logger.info("Update check failed (network): %s", e)
            return None

        remote_version = _safe_version(data.get("version", ""))
        local_version = _safe_version(Config.VERSION)
        if not remote_version or not local_version:
            return None

        if remote_version > local_version:
            logger.info("Update available: %s → %s", Config.VERSION, data["version"])
            return data

        logger.info("App is up-to-date (%s)", Config.VERSION)
        return None

    @staticmethod
    def download_installer(
        url: str,
        expected_sha256: str = "",
        progress_callback=None,
    ) -> str:
        """Download the installer to a temp directory.

        Args:
            url: Direct download URL for the installer .exe.
            expected_sha256: SHA-256 hex digest for integrity verification.
                Must be provided; raises RuntimeError if missing.
            progress_callback: Optional callable(bytes_downloaded, total_bytes).

        Returns:
            Path to the downloaded installer file.

        Raises:
            RuntimeError: On download failure, missing checksum, or checksum mismatch.
        """
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CBPOS-Updater"})
            resp = urllib.request.urlopen(req, timeout=60)
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"Download failed: {e}")

        total = int(resp.headers.get("Content-Length", 0))

        # Write to a temp file that persists after close (delete=False).
        suffix = ".exe" if url.lower().endswith(".exe") else ""
        tmp = tempfile.NamedTemporaryFile(prefix="CBPOSSetup_", suffix=suffix, delete=False)

        sha = hashlib.sha256()
        downloaded = 0
        try:
            while True:
                chunk = resp.read(64 * 1024)  # 64 KB chunks
                if not chunk:
                    break
                tmp.write(chunk)
                sha.update(chunk)
                downloaded += len(chunk)
                if progress_callback and total:
                    progress_callback(downloaded, total)
        except Exception:
            tmp.close()
            os.unlink(tmp.name)
            raise
        finally:
            tmp.close()
            resp.close()

        # Verify integrity — checksum is mandatory for security.
        if not expected_sha256:
            os.unlink(tmp.name)
            raise RuntimeError("Security error: No checksum provided in update manifest.")

        actual = sha.hexdigest()
        if actual.lower() != expected_sha256.lower():
            os.unlink(tmp.name)
            raise RuntimeError(
                f"Checksum mismatch — download may be corrupt.\nExpected: {expected_sha256}\nGot:      {actual}"
            )

        logger.info("Installer downloaded: %s (%d bytes)", tmp.name, downloaded)
        return tmp.name
