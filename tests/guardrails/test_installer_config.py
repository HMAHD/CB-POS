"""Guardrail tests for Phase 10A.3 Issue #815: Inno Setup 64-bit configuration and data safety."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISS_PATH = ROOT / "installer" / "cbpos.iss"


def test_installer_script_sets_64bit_architecture_mode():
    """cbpos.iss must configure 64-bit installer mode for Windows 10/11."""
    assert ISS_PATH.exists(), "installer/cbpos.iss must exist"
    text = ISS_PATH.read_text(encoding="utf-8")

    # 64-bit architecture restrictions and install mode
    assert re.search(r"^\s*ArchitecturesAllowed\s*=\s*x64compatible\s*$", text, re.MULTILINE), (
        "ArchitecturesAllowed=x64compatible required in cbpos.iss"
    )
    assert re.search(r"^\s*ArchitecturesInstallIn64BitMode\s*=\s*x64compatible\s*$", text, re.MULTILINE), (
        "ArchitecturesInstallIn64BitMode=x64compatible required in cbpos.iss"
    )

    # Core install flags
    assert re.search(r"^\s*UsePreviousAppDir\s*=\s*yes\s*$", text, re.MULTILINE), (
        "UsePreviousAppDir=yes required in cbpos.iss"
    )
    assert re.search(r"^\s*MinVersion\s*=\s*10\.0\s*$", text, re.MULTILINE), (
        "MinVersion=10.0 required in cbpos.iss (Windows 10 minimum)"
    )
    assert re.search(r"^\s*PrivilegesRequired\s*=\s*admin\s*$", text, re.MULTILINE), (
        "PrivilegesRequired=admin required in cbpos.iss"
    )


def test_installer_script_bridges_32bit_upgrade_and_cleans_legacy_keys():
    """cbpos.iss must use GetInstallDir to bridge HKLM32 upgrade path and clean up legacy uninstaller key."""
    text = ISS_PATH.read_text(encoding="utf-8")

    # DefaultDirName should invoke GetInstallDir to bridge 32-to-64-bit upgrade path
    assert re.search(r"^\s*DefaultDirName\s*=\s*\{code:GetInstallDir\}\s*$", text, re.MULTILINE), (
        "DefaultDirName={code:GetInstallDir} required in cbpos.iss to bridge 32-to-64-bit upgrades"
    )

    # Pascal script implementation checks
    assert "function GetInstallDir" in text, "GetInstallDir function must be implemented in [Code]"
    assert "HKLM32" in text, "GetInstallDir must check HKLM32 for legacy 32-bit install location"
    assert "{autopf}\\{#MyAppName}" in text, "GetInstallDir must fall back to {autopf}\\{#MyAppName}"

    # Cleanup of legacy 32-bit registry key in post-install
    assert "RegDeleteKeyIncludingSubkeys" in text or "RegDeleteKey" in text, (
        "Post-install must clean up legacy 32-bit uninstaller registry key"
    )


def test_installer_script_preserves_user_data_directory():
    """Neither [UninstallDelete] nor [InstallDelete] may ever delete %LOCALAPPDATA% user data."""
    text = ISS_PATH.read_text(encoding="utf-8")

    # Verify [UninstallDelete] section does not target localappdata
    if "[UninstallDelete]" in text:
        uninstall_delete_section = text.split("[UninstallDelete]")[1].split("[")[0]
        assert "{localappdata}" not in uninstall_delete_section.lower(), (
            "[UninstallDelete] must never target {localappdata} user data directory"
        )
        assert "cbpos.db" not in uninstall_delete_section.lower(), "[UninstallDelete] must never delete cbpos.db"
        assert ".encryption_key" not in uninstall_delete_section.lower(), (
            "[UninstallDelete] must never delete .encryption_key"
        )

    # Verify [InstallDelete] does not exist or does not target user data
    if "[InstallDelete]" in text:
        install_delete_section = text.split("[InstallDelete]")[1].split("[")[0]
        assert "{localappdata}" not in install_delete_section.lower(), (
            "[InstallDelete] must never target {localappdata} user data directory"
        )


def test_installer_script_checks_running_mutex():
    """Installer must verify CBPOSAppMutex before setup proceeds."""
    text = ISS_PATH.read_text(encoding="utf-8")
    assert "CheckForMutexes('CBPOSAppMutex')" in text, (
        "InitializeSetup must check CBPOSAppMutex to ensure running app is closed"
    )


def test_system_requirements_and_smartscreen_docs():
    """User documentation must specify Windows 10 (64-bit) and provide SmartScreen instructions."""
    readme_path = ROOT / "public-releases-readme.md"
    assert readme_path.exists(), "public-releases-readme.md must exist"
    readme_text = readme_path.read_text(encoding="utf-8")

    assert "Windows 10 (64-bit)" in readme_text, "Documentation must specify 64-bit Windows requirement"
    assert "SmartScreen" in readme_text, "Documentation must include SmartScreen warning instructions"
    assert "More info" in readme_text, "Documentation must tell users to click 'More info'"
    assert "Run anyway" in readme_text, "Documentation must tell users to click 'Run anyway'"
