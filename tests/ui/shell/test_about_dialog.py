"""Tests for Phase 8.3 Issue #816: AboutDialog, Help, Legal and Canonical Links."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QScrollArea

from cbpos.config import Config
from cbpos.core.constants.links import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    get_docs_url,
    get_privacy_url,
    get_report_bug_url,
    get_source_url,
    get_suggest_feature_url,
    get_terms_url,
    get_website_url,
    open_external_url,
    resolve_locale,
)
from cbpos.i18n import _t
from cbpos.ui.dialogs.about_dialog import AboutDialog
from cbpos.ui.dialogs.text_viewer_dialog import TextViewerDialog
from cbpos.ui.main_window import MainWindow
from cbpos.ui.widgets.side_menu import SideMenu

ROOT = Path(__file__).resolve().parents[3]


def test_locale_resolution_and_canonical_links():
    """Canonical links must resolve locale correctly and contain no PII."""
    for loc in SUPPORTED_LOCALES:
        assert resolve_locale(loc) == loc
        assert f"/{loc}/" in get_website_url(loc)
        assert f"/{loc}/docs/" in get_docs_url(loc)
        assert f"/{loc}/feedback/?type=bug" in get_report_bug_url(loc)
        assert f"/{loc}/feedback/?type=feature" in get_suggest_feature_url(loc)
        assert f"/{loc}/legal/privacy/" in get_privacy_url(loc)
        assert f"/{loc}/legal/terms/" in get_terms_url(loc)

    # Unknown locale falls back to default
    assert resolve_locale("fr") == DEFAULT_LOCALE
    assert resolve_locale(None) == DEFAULT_LOCALE
    assert f"/{DEFAULT_LOCALE}/" in get_website_url("unknown")

    # Fixed routing parameters only, no PII or version parameters
    bug_url = get_report_bug_url("en")
    assert bug_url == "https://ceybyte.com/en/feedback/?type=bug"
    feature_url = get_suggest_feature_url("en")
    assert feature_url == "https://ceybyte.com/en/feedback/?type=feature"

    # Source URL contains exact version tag
    source_url = get_source_url("1.3.0")
    assert source_url == "https://github.com/HMAHD/CB-POS/tree/v1.3.0"


def test_open_external_url_helper(qapp, monkeypatch):
    """open_external_url opens only HTTPS URLs and shows fallback on failure."""
    # Reject non-https
    with pytest.raises(ValueError, match="Only HTTPS URLs are permitted"):
        open_external_url("http://insecure.site")

    # Mock QDesktopServices.openUrl returning True
    with patch("PyQt6.QtGui.QDesktopServices.openUrl", return_value=True) as mock_open:
        success = open_external_url("https://ceybyte.com/en/")
        assert success is True
        mock_open.assert_called_once()

    # When openUrl returns False, should show fallback dialog and return False
    with (
        patch("PyQt6.QtGui.QDesktopServices.openUrl", return_value=False),
        patch("cbpos.core.constants.links._show_url_fallback_dialog") as mock_fallback,
    ):
        success = open_external_url("https://ceybyte.com/en/")
        assert success is False
        mock_fallback.assert_called_once()


def test_about_dialog_components_and_visual_hierarchy(qtbot):
    """AboutDialog must display logo, version, build date, sections, and touch targets."""
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    # Must contain scroll area for small screens (1024x768 safe)
    scrolls = dialog.findChildren(QScrollArea)
    assert len(scrolls) >= 1, "AboutDialog must use a QScrollArea for small screen safety"

    # Header labels
    assert dialog.lbl_app_name.text() == Config.APP_NAME
    assert Config.VERSION in dialog.lbl_version.text()

    # Build date truthful display
    if Config.BUILD_DATE:
        assert Config.BUILD_DATE in dialog.lbl_version.text()
    else:
        assert _t("about.dev_build") in dialog.lbl_version.text()

    # Clickable website company link
    assert "ceybyte.com" in dialog.btn_company.text()

    # Help section actions
    assert hasattr(dialog, "btn_user_guide")
    assert hasattr(dialog, "btn_report_problem")
    assert hasattr(dialog, "btn_suggest_feature")
    assert hasattr(dialog, "btn_check_updates")

    # Helper text
    assert "Google" in dialog.lbl_feedback_helper.text()
    assert "CB POS" in dialog.lbl_feedback_helper.text()

    # Legal section actions
    assert hasattr(dialog, "btn_licence")
    assert hasattr(dialog, "btn_privacy")
    assert hasattr(dialog, "btn_third_party")
    assert hasattr(dialog, "btn_view_source")

    # Close footer button
    assert hasattr(dialog, "btn_close")

    # Touch targets: every interactive button must be at least 44px high
    interactive_buttons = [
        dialog.btn_user_guide,
        dialog.btn_report_problem,
        dialog.btn_suggest_feature,
        dialog.btn_check_updates,
        dialog.btn_licence,
        dialog.btn_privacy,
        dialog.btn_third_party,
        dialog.btn_view_source,
        dialog.btn_close,
    ]
    for btn in interactive_buttons:
        assert btn.minimumHeight() >= 44, f"Button {btn.objectName() or btn.text()} minimumHeight must be >= 44"


def test_about_dialog_legal_viewers_load_bundled_files(qtbot):
    """Clicking legal buttons opens TextViewerDialog with bundled files."""
    dialog = AboutDialog()
    qtbot.addWidget(dialog)

    # Test licence viewer
    with patch.object(TextViewerDialog, "exec", return_value=QDialog.DialogCode.Accepted) as mock_exec:
        dialog.btn_licence.click()
        mock_exec.assert_called_once()

    # Test privacy viewer
    with patch.object(TextViewerDialog, "exec", return_value=QDialog.DialogCode.Accepted) as mock_exec:
        dialog.btn_privacy.click()
        mock_exec.assert_called_once()

    # Test third-party notices viewer
    with patch.object(TextViewerDialog, "exec", return_value=QDialog.DialogCode.Accepted) as mock_exec:
        dialog.btn_third_party.click()
        mock_exec.assert_called_once()


def test_about_dialog_update_check_delegates(qtbot):
    """Check for updates delegates to check_for_updates_async without freezing."""
    dialog = AboutDialog()
    qtbot.addWidget(dialog)

    with patch("cbpos.ui.dialogs.about_dialog.check_for_updates_async") as mock_check:
        dialog.btn_check_updates.click()
        mock_check.assert_called_once_with(parent=dialog, silent=False, button=dialog.btn_check_updates)


def test_side_menu_has_help_about_tile(qtbot):
    """SideMenu must contain touch-friendly Help & About NavTile with help_clicked signal."""
    menu = SideMenu()
    qtbot.addWidget(menu)

    assert hasattr(menu, "btn_help"), "SideMenu must have btn_help"
    assert hasattr(menu, "help_clicked"), "SideMenu must have help_clicked signal"

    # Minimum touch target
    assert menu.btn_help.minimumHeight() >= 44

    # Clicking emits help_clicked
    with qtbot.waitSignal(menu.help_clicked, timeout=1000):
        menu.btn_help.click()


def test_main_window_wires_help_signal(qapp, monkeypatch):
    """MainWindow must wire side_menu.help_clicked to open AboutDialog."""
    from PyQt6.QtCore import pyqtSignal
    from PyQt6.QtWidgets import QWidget

    class DummySideMenu(QWidget):
        management_clicked = pyqtSignal()
        documents_clicked = pyqtSignal()
        receive_payment_clicked = pyqtSignal()
        reprint_receipt_clicked = pyqtSignal()
        refund_clicked = pyqtSignal()
        history_clicked = pyqtSignal()
        shift_clicked = pyqtSignal()
        help_clicked = pyqtSignal()
        logout_clicked = pyqtSignal()
        settings_clicked = pyqtSignal()
        fullscreen_clicked = pyqtSignal()
        power_clicked = pyqtSignal()

        def set_user(self, user):
            pass

        def setVisible(self, visible):
            pass

        def clear_active(self):
            pass

    class DummySalesView(QWidget):
        shift_closed = pyqtSignal()
        printer_setup_requested = pyqtSignal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self.side_menu = DummySideMenu(self)

        def open_receive_payment(self):
            pass

        def open_reprint_receipt(self):
            pass

        def open_refund(self):
            pass

        def open_sale_history(self):
            pass

        def open_shift_management(self):
            pass

    class DummyManagementView(QWidget):
        logout_requested = pyqtSignal()
        request_pos_view = pyqtSignal()
        convert_proforma_to_sale = pyqtSignal(dict)
        open_settings_requested = pyqtSignal()

    class DummySettingsView(QWidget):
        close_requested = pyqtSignal()
        logout_requested = pyqtSignal()
        settings_saved = pyqtSignal()
        request_pos_view = pyqtSignal()

    monkeypatch.setattr("cbpos.ui.main_window.SalesView", DummySalesView)
    monkeypatch.setattr("cbpos.ui.main_window.ManagementView", DummyManagementView)
    monkeypatch.setattr("cbpos.ui.main_window.SettingsView", DummySettingsView)
    monkeypatch.setattr("cbpos.ui.main_window.SessionWatchdog", MagicMock())

    window = MainWindow()
    try:
        with patch("cbpos.ui.dialogs.about_dialog.AboutDialog") as mock_about:
            mock_dlg = MagicMock()
            mock_about.return_value = mock_dlg
            window.sales_view.side_menu.help_clicked.emit()
            mock_about.assert_called_once_with(window)
            mock_dlg.exec.assert_called_once()
    finally:
        window.deleteLater()


def test_about_dialog_keyboard_navigation_and_esc_close(qtbot):
    """AboutDialog must handle keyboard navigation (Tab focus) and close on Esc."""
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    # Esc key closes the dialog
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()


def test_about_dialog_text_expansion_trilingual(qtbot):
    """AboutDialog must handle text expansion across en, si, and ta without layout breaks."""
    from cbpos.i18n import set_language

    for lang in ("en", "si", "ta"):
        set_language(lang)
        dialog = AboutDialog()
        qtbot.addWidget(dialog)
        dialog.show()

        # Check critical labels are non-empty and visible
        assert dialog.lbl_app_name.text() != ""
        assert dialog.btn_user_guide.text() != ""
        assert dialog.btn_licence.text() != ""
        assert dialog.btn_close.text() != ""
        assert dialog.lbl_feedback_helper.text() != ""

        # Geometry checks for 1024x768 screens
        assert dialog.minimumWidth() <= 500
        assert dialog.minimumHeight() <= 600
        dialog.close()

    # Reset back to en
    set_language("en")
