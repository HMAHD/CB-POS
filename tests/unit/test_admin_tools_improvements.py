"""Tests for issue #621 (UI-051): Admin Tools full log entries, modal detail dialog, live filtering, and copyable database path."""

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from cbpos.core.services.error_log_service import ErrorLogService
from cbpos.ui.dialogs.log_detail_dialog import LogDetailDialog
from cbpos.ui.views.admin_tools_view import AdminToolsView

pytestmark = pytest.mark.usefixtures("qapp")


def test_error_log_service_preserves_multiline_traceback(tmp_path, monkeypatch):
    """Multi-line entries and tracebacks should be preserved in entry['message']."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "cbpos.log"

    log_content = (
        "2026-10-15 12:00:00,123 | ERROR    | main | Unhandled crash\n"
        "Traceback (most recent call last):\n"
        '  File "main.py", line 42, in boom\n'
        '    raise RuntimeError("simulated crash")\n'
        "RuntimeError: simulated crash\n"
        "2026-10-15 12:05:00,456 | WARNING  | auth | Failed attempt\n"
    )
    log_file.write_text(log_content, encoding="utf-8")

    monkeypatch.setattr(ErrorLogService, "LOG_DIR", log_dir)

    entries = ErrorLogService.read_logs()
    assert len(entries) == 2

    crash_entry = next(e for e in entries if e["level"] == "ERROR")
    assert "Traceback (most recent call last):" in crash_entry["message"]
    assert 'raise RuntimeError("simulated crash")' in crash_entry["message"]
    assert "RuntimeError: simulated crash" in crash_entry["message"]

    # Search filter should match text within the traceback
    searched = ErrorLogService.read_logs(search="simulated crash")
    assert len(searched) == 1
    assert searched[0]["level"] == "ERROR"


def test_admin_tools_db_copy_and_open_buttons(tmp_path, monkeypatch):
    """Database tab should provide copy and open folder buttons for the db path."""
    view = AdminToolsView()
    assert hasattr(view, "btn_copy_db_path")
    assert hasattr(view, "btn_open_db_folder")

    db_file = tmp_path / "test.db"
    db_file.write_text("sqlite")
    view.lbl_db_path.setText(str(db_file))

    # Test copy puts path on clipboard
    view._copy_db_path()
    assert QApplication.clipboard().text() == str(db_file)

    # Test open folder calls QDesktopServices.openUrl
    opened_urls = []
    from PyQt6.QtGui import QDesktopServices

    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened_urls.append(url.toLocalFile()))
    view._open_db_folder()
    assert len(opened_urls) == 1
    assert Path(opened_urls[0]).resolve() == tmp_path.resolve()

    # If path is placeholder or empty, openUrl shouldn't be called
    view.lbl_db_path.setText("--")
    view._open_db_folder()
    assert len(opened_urls) == 1

    view.close()
    view.deleteLater()


def test_admin_tools_live_filtering_and_scanner_box_hidden(tmp_path, monkeypatch):
    """Live search debounce timer should exist, and empty scanner boxes should be hidden."""
    view = AdminToolsView()
    view.tabs.setCurrentIndex(2)
    view.show()

    # Live filter timer
    assert hasattr(view, "_search_timer")
    assert view._search_timer.isSingleShot()
    assert view._search_timer.interval() == 250

    # Typing in search triggers timer
    view.input_log_search.setText("error")
    assert view._search_timer.isActive()
    view._search_timer.stop()

    # Scanner status/detection labels should be hidden when empty (no empty gray box)
    assert not view.lbl_scanner_status.isVisible()
    assert not view.lbl_scanner_detection.isVisible()

    # When scanner text is entered, status becomes visible
    view._on_scanner_input("123456789")
    assert view.lbl_scanner_status.isVisible()

    # When cleared, hidden again
    view._clear_scanner()
    assert not view.lbl_scanner_status.isVisible()
    assert not view.lbl_scanner_detection.isVisible()

    # View Details button replaces the old cramped bottom inline panel
    assert hasattr(view, "btn_view_details")
    assert not hasattr(view, "txt_log_details")
    assert not view.btn_view_details.isEnabled()

    # Set up mock entries with a multi-line message
    view._current_log_entries = [
        {
            "timestamp": "2026-10-15 12:00:00",
            "level": "ERROR",
            "source": "main",
            "message": "Crash occurred\nTraceback (most recent call last):\n  File boom.py, line 1",
        }
    ]
    view.log_pagination.set_total(1)
    view._populate_log_page()

    # Table item message should only be the first line, with full message in tooltip
    msg_item = view.log_table.item(0, 3)
    assert msg_item.text() == "Crash occurred"
    assert "Traceback" in msg_item.toolTip()

    # Selecting the row enables btn_view_details
    view.log_table.selectRow(0)
    assert view.btn_view_details.isEnabled()

    # Triggering detail dialog via button click or double-click opens LogDetailDialog
    with patch.object(LogDetailDialog, "exec") as mock_exec:
        view.btn_view_details.click()
        assert mock_exec.called

    with patch.object(LogDetailDialog, "exec") as mock_exec:
        view.log_table.doubleClicked.emit(view.log_table.model().index(0, 0))
        assert mock_exec.called

    # Clearing selection disables btn_view_details
    view.log_table.clearSelection()
    assert not view.btn_view_details.isEnabled()

    # When nothing selected, _open_log_detail_dialog does nothing
    with patch.object(LogDetailDialog, "exec") as mock_exec:
        view._open_log_detail_dialog()
        assert not mock_exec.called

    view.close()
    view.deleteLater()


@pytest.mark.parametrize(
    ("delta_args", "expected"),
    [
        ({"seconds": 15}, "Just now"),
        ({"minutes": 1}, "1 minute ago"),
        ({"minutes": 25}, "25 minutes ago"),
        ({"hours": 1}, "1 hour ago"),
        ({"hours": 5}, "5 hours ago"),
        ({"days": 1}, "1 day ago"),
        ({"days": 4}, "4 days ago"),
        ({"days": 7}, "1 week ago"),
        ({"days": 14}, "2 weeks ago"),
        ({"days": 60}, "2 months ago"),
        ({"days": 400}, "1 year ago"),
    ],
)
def test_format_relative_time(delta_args, expected):
    from datetime import datetime, timedelta

    from cbpos.core.utils.formatters import format_relative_time

    base = datetime(2026, 10, 16, 15, 0, 0)
    target = base - timedelta(**delta_args)
    assert format_relative_time(target, now=base) == expected
    # Also test formatted string parsing with and without milliseconds
    str_target = target.strftime("%Y-%m-%d %H:%M:%S")
    assert format_relative_time(str_target, now=base) == expected
    str_target_ms = target.strftime("%Y-%m-%d %H:%M:%S,123")
    assert format_relative_time(str_target_ms, now=base) == expected


def test_log_detail_dialog():
    """LogDetailDialog should display full message, status pill, relative time, and copy details to clipboard."""
    entry = {
        "timestamp": "2026-10-15 12:00:00,123",
        "level": "CRITICAL",
        "source": "cbpos.crash",
        "message": (
            "Unhandled exception\n"
            "Traceback (most recent call last):\n"
            '  File "main.py", line 10, in <module>\n'
            "ZeroDivisionError: division by zero"
        ),
    }

    dialog = LogDetailDialog(entry)
    assert dialog.windowTitle() != ""
    assert dialog.lbl_level.text() == "CRITICAL"
    assert dialog.lbl_level.property("level") == "CRITICAL"
    assert hasattr(dialog, "lbl_relative_time")
    assert hasattr(dialog, "lbl_exact_time")
    assert "(2026-10-15 12:00:00)" in dialog.lbl_exact_time.text()
    assert dialog.lbl_source.text() == "cbpos.crash"
    assert dialog.txt_message.isReadOnly()
    assert "ZeroDivisionError: division by zero" in dialog.txt_message.toPlainText()

    # Copy details puts formatted string to clipboard
    dialog._copy_details()
    copied = QApplication.clipboard().text()
    assert "Timestamp: 2026-10-15 12:00:00,123" in copied
    assert "Level:     CRITICAL" in copied
    assert "Source:    cbpos.crash" in copied
    assert "ZeroDivisionError: division by zero" in copied

    dialog.btn_close.click()
    dialog.close()
    dialog.deleteLater()
