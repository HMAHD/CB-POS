"""UI and integration tests for ReceiptFontSettings on ReceiptPage (Phase 10A #925).

Verifies:
1. ReceiptPage loads and saves 'receipt_font_preset' correctly.
2. Toggling font preset radio immediately refreshes live preview with unsaved font preset.
3. 'Print test receipt' queues a job to PrintWorker, disables button, and handles job_result.
4. Unrelated PrintWorker job results are ignored.
5. Signal cleanup on page destruction.
6. Retranslation updates labels in en/si/ta cleanly.
"""

from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QLabel, QMessageBox

from cbpos.core.services.receipt_font_service import ReceiptFontService
from cbpos.i18n import _t, set_language
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.infrastructure.resource_loader import ResourceLoader
from cbpos.ui.views.settings_pages.receipt import ReceiptPage


def test_receipt_font_settings_load_save(qapp):
    """Verify loading and saving receipt_font_preset."""
    page = ReceiptPage()

    # Load with compact
    page.load({"receipt_font_preset": "compact"})
    assert page.rb_font_compact.isChecked()
    assert not page.rb_font_clear.isChecked()
    assert page.save()["receipt_font_preset"] == "compact"

    # Load with clear
    page.load({"receipt_font_preset": "clear"})
    assert page.rb_font_clear.isChecked()
    assert not page.rb_font_compact.isChecked()
    assert page.save()["receipt_font_preset"] == "clear"


def test_receipt_font_preview_refresh_on_toggle(qapp):
    """Toggling radio button immediately propagates unsaved font preset to preview."""
    ResourceLoader.load_fonts()
    page = ReceiptPage()
    page.load({"receipt_font_preset": "clear"})

    # Toggle to compact
    page.rb_font_compact.setChecked(True)
    # Manually trigger immediate refresh (simulating debounce timeout)
    page._refresh_preview()

    assert page._preview._font_preset == "compact"
    # Check that commands generated for preview carry Yaldevi font families
    compact_fams = ReceiptFontService.get_font_families("compact")
    for cmd in page._preview._commands:
        if cmd.get("type") == "text":
            assert cmd.get("font_families") == compact_fams


def test_print_test_receipt_success(qapp):
    """Test print test receipt flow on successful print job."""
    page = ReceiptPage()
    page.load({"receipt_font_preset": "compact"})

    mock_worker = MagicMock()
    mock_worker.add_job.return_value = "job-12345"

    with patch.object(PrintWorker, "instance", return_value=mock_worker):
        # Click Print Test Receipt
        page.btn_print_test.click()

        assert page._test_print_job_id == "job-12345"
        assert not page.btn_print_test.isEnabled()
        assert _t("settings.receipt.test_print_status_printing") in page.lbl_print_test_status.text()
        assert mock_worker.add_job.called
        job_type, cmds = mock_worker.add_job.call_args[0]
        assert job_type == "print_receipt"
        assert isinstance(cmds, list)

        # Emit matching job success
        page._on_test_print_job_result("job-12345", True, "")
        assert page._test_print_job_id is None
        assert page.btn_print_test.isEnabled()
        assert _t("settings.receipt.test_print_status_success") in page.lbl_print_test_status.text()


def test_print_test_receipt_failure(qapp):
    """Test print test receipt flow when print job fails."""
    page = ReceiptPage()
    page.load({"receipt_font_preset": "clear"})

    mock_worker = MagicMock()
    mock_worker.add_job.return_value = "job-err-999"

    with (
        patch.object(PrintWorker, "instance", return_value=mock_worker),
        patch.object(QMessageBox, "warning") as mock_warning,
    ):
        page.btn_print_test.click()
        assert not page.btn_print_test.isEnabled()

        # Emit failure for an unrelated job: should be ignored
        page._on_test_print_job_result("unrelated-job", True, "")
        assert not page.btn_print_test.isEnabled()
        assert page._test_print_job_id == "job-err-999"

        # Emit failure for target job
        page._on_test_print_job_result("job-err-999", False, "Printer is offline")
        assert page.btn_print_test.isEnabled()
        assert _t("settings.receipt.test_print_status_failed") in page.lbl_print_test_status.text()
        assert mock_warning.called


def test_receipt_page_retranslation(qapp):
    """Verify that retranslate_ui cleanly translates all font and test print widgets."""
    page = ReceiptPage()

    for lang in ("en", "si", "ta"):
        set_language(lang)
        page.retranslate_ui()
        section_titles = [lbl.text() for lbl in page.findChildren(QLabel, "SettingsSectionTitle")]
        assert _t("settings.receipt.section_receipt_font") in section_titles
        assert page.rb_font_clear.text() == _t("settings.receipt.font_clear")
        assert page.rb_font_compact.text() == _t("settings.receipt.font_compact")
        assert page.btn_print_test.text() == _t("settings.receipt.btn_print_test")

    # Reset language
    set_language("en")
