"""Unit tests for UpdateService (#808)."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.services.update_service import UpdateService


def _fake_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = None
    return resp


def test_issue_808_min_version_marks_required():
    """Manifest min_version higher than current version marks update as required."""
    with patch("cbpos.config.Config.VERSION", "1.2.0"):
        manifest = {
            "version": "1.3.0",
            "min_version": "1.2.5",
            "release_date": "2026-09-03",
            "download_url": "https://example.com/setup.exe",
            "changelog": "Critical security fix",
            "sha256": "abc",
        }
        with patch("urllib.request.urlopen", return_value=_fake_response(manifest)):
            result = UpdateService.check_for_update()
            assert result is not None
            assert result["version"] == "1.3.0"
            assert result.get("is_required") is True


def test_issue_808_min_version_lower_than_current_is_optional():
    """Manifest min_version lower or equal to current version is not required."""
    with patch("cbpos.config.Config.VERSION", "1.2.0"):
        # Case 1: min_version lower than current version
        manifest = {
            "version": "1.3.0",
            "min_version": "1.1.0",
            "release_date": "2026-09-03",
            "download_url": "https://example.com/setup.exe",
            "changelog": "New features",
            "sha256": "abc",
        }
        with patch("urllib.request.urlopen", return_value=_fake_response(manifest)):
            result = UpdateService.check_for_update()
            assert result is not None
            assert result["version"] == "1.3.0"
            assert result.get("is_required") is False

        # Case 2: min_version equal to current version
        manifest["min_version"] = "1.2.0"
        with patch("urllib.request.urlopen", return_value=_fake_response(manifest)):
            result = UpdateService.check_for_update()
            assert result is not None
            assert result.get("is_required") is False


def test_issue_808_up_to_date_returns_none():
    """When remote version is <= local version, returns None without raising."""
    with patch("cbpos.config.Config.VERSION", "1.3.0"):
        manifest = {
            "version": "1.3.0",
            "min_version": "1.0.0",
            "release_date": "2026-09-03",
            "download_url": "https://example.com/setup.exe",
            "changelog": "",
            "sha256": "abc",
        }
        with patch("urllib.request.urlopen", return_value=_fake_response(manifest)):
            result = UpdateService.check_for_update()
            assert result is None


def test_issue_808_failure_vs_up_to_date_distinct():
    """Network or JSON failure raises an exception so callers never confuse it with up-to-date."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        with pytest.raises(RuntimeError, match="Network error"):
            UpdateService.check_for_update()


def test_issue_808_setting_off_skips_startup_check():
    """When auto_update_check is False in settings, deferred startup check does not run."""
    from cbpos.core.services.config_service import ConfigService

    def fake_get(key, *args):
        if key == "auto_update_check":
            return False
        return None

    with patch.object(ConfigService, "get", side_effect=fake_get):
        assert UpdateService.should_check_on_startup() is False

    def fake_get_true(key, *args):
        if key == "auto_update_check":
            return True
        return None

    with patch.object(ConfigService, "get", side_effect=fake_get_true):
        assert UpdateService.should_check_on_startup() is True


def test_issue_808_setting_string_boolean_parsed_properly():
    """String booleans (e.g. 'false', '0') are parsed properly and do not enable checks."""
    from cbpos.core.services.config_service import ConfigService

    with patch.object(ConfigService, "get", return_value="false"):
        assert UpdateService.should_check_on_startup() is False

    with patch.object(ConfigService, "get", return_value="0"):
        assert UpdateService.should_check_on_startup() is False

    with patch.object(ConfigService, "get", return_value="true"):
        assert UpdateService.should_check_on_startup() is True


def test_issue_808_setting_fails_closed_on_error():
    """On config read failure, should_check_on_startup fails closed (returns False)."""
    from cbpos.core.services.config_service import ConfigService

    with patch.object(ConfigService, "get", side_effect=RuntimeError("DB offline")):
        assert UpdateService.should_check_on_startup() is False
