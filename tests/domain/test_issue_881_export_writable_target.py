"""Regression tests for Issue #881: Exports to USB or other drives."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from cbpos.core.services.export_service import ExportService
from cbpos.core.utils.paths import ensure_writable_target, format_export_error


def test_issue_881_export_to_other_drive_path_succeeds(tmp_path, monkeypatch):
    """Saving to a location outside home/temp (e.g. simulated USB drive) succeeds (#881)."""
    # Simulate that home and temp are different directories entirely
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    fake_temp = tmp_path / "fake_temp"
    fake_temp.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(fake_temp))

    # Destination on a "different drive" (outside fake_home and system temp)
    usb_drive = tmp_path / "usb_drive"
    usb_drive.mkdir()
    export_file = usb_drive / "sales_report.csv"

    df = pd.DataFrame({"Item": ["Rice", "Sugar"], "Price": [250.0, 180.0]})
    svc = ExportService()
    svc.export_to_csv(df, str(export_file))

    assert export_file.exists()
    content = export_file.read_text(encoding="utf-8")
    assert "Rice" in content
    assert "250.0" in content


def test_issue_881_unwritable_parent_raises(tmp_path):
    """When the parent directory is not writable, ensure_writable_target raises PermissionError."""
    readonly_dir = tmp_path / "readonly_usb"
    readonly_dir.mkdir()
    target_file = readonly_dir / "report.xlsx"

    # Make readonly_dir unwritable
    with patch("os.access", return_value=False):
        with pytest.raises(PermissionError):
            ensure_writable_target(str(target_file))


def test_issue_881_relative_path_raises():
    """Relative paths are rejected for safety."""
    with pytest.raises(ValueError, match="Path must be absolute"):
        ensure_writable_target("relative/path/report.csv")


def test_issue_881_path_traversal_raises(tmp_path):
    """Path traversal sequences are rejected."""
    traversal_path = str(tmp_path / ".." / "traversal.csv")
    with pytest.raises(ValueError, match="Path traversal detected"):
        ensure_writable_target(traversal_path)


def test_issue_881_missing_parent_raises(tmp_path):
    """Non-existent parent folder raises FileNotFoundError."""
    missing_dir = tmp_path / "non_existent_folder"
    target_file = missing_dir / "report.csv"
    with pytest.raises(FileNotFoundError):
        ensure_writable_target(str(target_file))


def test_issue_881_format_export_error():
    """format_export_error produces translated user-friendly message for unwritable destination."""
    folder = "/mnt/flash_storage"
    err = PermissionError(f"Folder is not writable: {folder}")
    err.filename = folder
    msg = format_export_error(err, f"{folder}/sales.csv")
    assert folder in msg
    assert "USB drive" in msg or "ලිවීම" in msg or "write-protected" in msg
