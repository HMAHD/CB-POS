"""UI tests for SystemPage Updates tab and UpdateDialog (#808)."""

import pytest
from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QPushButton

from cbpos.ui.dialogs.update_dialog import UpdateDialog
from cbpos.ui.views.settings_pages.system import SystemPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_system_page_has_updates_tab(qapp):
    """SystemPage has an Updates tab with auto-update checkbox, helper label, and check now button."""
    page = SystemPage()
    assert hasattr(page, "_tab_updates")
    assert page.tabs.indexOf(page._tab_updates) >= 0
    assert hasattr(page, "chk_auto_update")
    assert hasattr(page, "lbl_auto_update_help")
    assert hasattr(page, "btn_check_updates")
    assert isinstance(page.btn_check_updates, QPushButton)
    assert page.lbl_auto_update_help.wordWrap() is True


def test_system_page_load_and_save_auto_update_setting(qapp):
    """SystemPage loads and saves auto_update_check boolean setting."""
    page = SystemPage()
    # Default is True
    page.load({})
    assert page.chk_auto_update.isChecked() is True
    saved = page.save()
    assert saved.get("auto_update_check") is True

    # When False
    page.load({"auto_update_check": False})
    assert page.chk_auto_update.isChecked() is False
    saved = page.save()
    assert saved.get("auto_update_check") is False


def test_update_dialog_optional_update(qapp):
    """Optional update shows Remind me later button and standard title."""
    from cbpos.i18n import _t

    manifest = {
        "version": "1.4.0",
        "release_date": "2026-10-01",
        "download_url": "https://example.com/setup.exe",
        "changelog": "- New features\n- Faster checkout",
        "sha256": "abc123",
        "is_required": False,
    }
    dlg = UpdateDialog(manifest)
    assert dlg._is_required is False
    assert dlg._btn_update.isHidden() is False
    assert dlg._btn_skip.isHidden() is False
    assert dlg._btn_skip.text() == _t("update.remind_later")
    assert dlg.lbl_required_notice.isHidden() is True
    assert dlg.findChild(QPlainTextEdit) is not None
    cl_widget = dlg.findChild(QPlainTextEdit)
    assert cl_widget.isReadOnly() is True
    assert "- New features" in cl_widget.toPlainText()


def test_update_dialog_required_update(qapp):
    """Required update has no 'Remind me later' button and shows required update notice."""
    from cbpos.i18n import _t

    manifest = {
        "version": "1.4.0",
        "min_version": "1.3.5",
        "release_date": "2026-10-01",
        "download_url": "https://example.com/setup.exe",
        "changelog": "Critical bug fix",
        "sha256": "abc123",
        "is_required": True,
    }
    dlg = UpdateDialog(manifest)
    assert dlg._is_required is True
    assert dlg._btn_skip.text() == _t("common.close")
    assert dlg.lbl_required_notice.isHidden() is False


def test_update_dialog_plain_text_changelog_escapes_html(qapp):
    """Changelog is displayed as plain text and not rendered as HTML markup."""
    raw_text = "Fix <script>alert(1)</script> and <b>tag</b> issue"
    manifest = {
        "version": "1.4.0",
        "download_url": "https://example.com/setup.exe",
        "changelog": raw_text,
        "sha256": "abc123",
    }
    dlg = UpdateDialog(manifest)
    cl_widget = dlg.findChild(QPlainTextEdit)
    assert cl_widget is not None
    assert cl_widget.toPlainText() == raw_text
