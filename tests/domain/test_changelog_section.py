"""Tests for scripts/changelog_section.py (#808)."""

from scripts.changelog_section import extract_changelog_section

SAMPLE_CHANGELOG = """# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Unreleased feature A

## [1.3.0] - 2026-09-03

### Added — Multi-Terminal LAN Sync
- Multi-terminal LAN sync architecture
- Sync Server (sync_server.py)

### Changed
- Improved error messages

## [1.2.2] - 2026-08-01

### Fixed
- Fixed a bug in receipt calculation
"""


def test_extracts_version_section():
    section = extract_changelog_section("1.3.0", SAMPLE_CHANGELOG)
    assert "### Added — Multi-Terminal LAN Sync" in section
    assert "Sync Server (sync_server.py)" in section
    assert "### Changed" in section
    assert "Unreleased feature A" not in section
    assert "Fixed a bug in receipt calculation" not in section


def test_extracts_version_section_with_v_prefix():
    section = extract_changelog_section("v1.3.0", SAMPLE_CHANGELOG)
    assert "### Added — Multi-Terminal LAN Sync" in section


def test_missing_version_returns_empty():
    section = extract_changelog_section("9.9.9", SAMPLE_CHANGELOG)
    assert section == ""
