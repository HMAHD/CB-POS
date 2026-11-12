"""Guardrail tests for Phase 8.3 Issue #817: GPLv3, privacy notice, and third-party notices."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_license_file_exists_and_is_gplv3():
    """LICENSE must contain unmodified GNU GPLv3 text with CB POS copyright notice."""
    license_path = ROOT / "LICENSE"
    assert license_path.exists(), "LICENSE file must exist at repository root"

    text = license_path.read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 29 June 2007" in text
    assert "Everyone is permitted to copy and distribute verbatim copies" in text
    assert "Ceylon Byte" in text or "CB POS" in text
    assert "TERMS AND CONDITIONS" in text
    # GPLv3 Section 10 forbids adding further restrictions
    assert "no resale" not in text.lower()
    assert "commercial use prohibited" not in text.lower()


def test_installer_script_has_license_file():
    """Inno Setup installer script must specify LicenseFile= pointing to LICENSE."""
    iss_path = ROOT / "installer" / "cbpos.iss"
    assert iss_path.exists(), "installer/cbpos.iss must exist"

    text = iss_path.read_text(encoding="utf-8")
    match = re.search(r"^\s*LicenseFile\s*=\s*(.+)$", text, re.MULTILINE)
    assert match is not None, "installer/cbpos.iss must specify LicenseFile="
    license_target = match.group(1).strip().strip('"')
    assert "LICENSE" in license_target, f"LicenseFile must reference LICENSE, got: {license_target}"


def test_pyinstaller_spec_bundles_legal_files():
    """cbpos.spec must bundle LICENSE, PRIVACY.md, and THIRD_PARTY_NOTICES.txt."""
    spec_path = ROOT / "cbpos.spec"
    assert spec_path.exists(), "cbpos.spec must exist"

    text = spec_path.read_text(encoding="utf-8")
    for filename in ("LICENSE", "PRIVACY.md", "THIRD_PARTY_NOTICES.txt"):
        assert filename in text, f"cbpos.spec datas must bundle {filename}"


def test_privacy_notice_covers_verified_network_categories():
    """PRIVACY.md must exist, be marked DRAFT, and accurately cover all verified network categories."""
    privacy_path = ROOT / "PRIVACY.md"
    assert privacy_path.exists(), "PRIVACY.md must exist"

    text = privacy_path.read_text(encoding="utf-8")
    assert "DRAFT — OWNER AND LEGAL REVIEW REQUIRED BEFORE PUBLIC RELEASE" in text

    # All verified categories must be explicitly addressed
    assert "update" in text.lower()
    assert "smtp" in text.lower() or "email" in text.lower()
    assert "lan sync" in text.lower() or "local network" in text.lower()
    assert "postgresql" in text.lower()
    assert "ceybyte.com" in text.lower()
    assert "google" in text.lower()
    assert "localappdata" in text.lower() or "appdata" in text.lower()
    assert "telemetry" in text.lower() or "analytics" in text.lower()

    # Crucial protections
    assert "does not automatically send shop data" in text.lower() or "no data is sent automatically" in text.lower()


def test_release_workflow_includes_notices_and_source_url():
    """The release workflow must generate third-party notices and publish exact source link."""
    workflow_path = ROOT / ".github" / "workflows" / "release.yml"
    assert workflow_path.exists(), ".github/workflows/release.yml must exist"

    text = workflow_path.read_text(encoding="utf-8")
    assert "gen_third_party_notices.py" in text, "Workflow must run gen_third_party_notices.py before build"
    assert "source_url" in text, "latest.json generation must include source_url"
    assert "https://github.com/HMAHD/CB-POS/tree/v" in text, "Exact-version source link must be published"


def test_third_party_notices_generation_and_completeness():
    """THIRD_PARTY_NOTICES.txt must be generated deterministically and cover all runtime dependencies."""
    script_path = ROOT / "scripts" / "gen_third_party_notices.py"
    assert script_path.exists(), "scripts/gen_third_party_notices.py must exist"

    # Run generator to test exit code and output
    proc = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
    assert proc.returncode == 0, f"gen_third_party_notices.py failed: {proc.stderr}"

    notices_path = ROOT / "THIRD_PARTY_NOTICES.txt"
    assert notices_path.exists(), "THIRD_PARTY_NOTICES.txt must exist"

    text = notices_path.read_text(encoding="utf-8")

    # Key runtime packages
    assert "PyQt6" in text
    assert "SQLAlchemy" in text
    assert "alembic" in text
    assert "pydantic" in text
    assert "bcrypt" in text
    assert "cryptography" in text
    assert "reportlab" in text
    assert "pandas" in text

    # Bundled assets not in standard pypi dependencies
    assert "Qt" in text
    assert "Font Awesome" in text
    assert "Noto Sans" in text
    assert "Sinhala" in text
    assert "Tamil" in text


def test_notices_fail_closed_on_missing_license(monkeypatch):
    """Generator must fail closed (raise RuntimeError) if a package lacks license info."""
    # Test an unknown dummy package that has neither installed metadata nor an override
    import pytest

    from scripts.gen_third_party_notices import extract_package_notice

    with pytest.raises(RuntimeError, match="unknown or missing licence information"):
        extract_package_notice("nonexistent-unlicensed-package-12345", "1.0.0")
