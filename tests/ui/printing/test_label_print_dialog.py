"""UI and integration tests for LabelPrintDialog (#819)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.label_print_dialog import LabelPrintDialog


def _make_dummy_product(
    name_en: str = "Test Tea 100g",
    name_si: str = "ටෙස්ට් තේ 100g",
    name_ta: str = "டெஸ்ட் தேநீர் 100g",
    barcode: str = "4006381333931",
    price: Decimal = Decimal("450.00"),
):
    prod = MagicMock()
    prod.id = 101
    prod.name_en = name_en
    prod.name_si = name_si
    prod.name_ta = name_ta
    prod.barcode = barcode
    prod.price = price

    def _get_display_name(lang: str | None = None) -> str:
        lang = (lang or "en").lower()
        if lang == "si" and (prod.name_si or "").strip():
            return prod.name_si.strip()
        if lang == "ta" and (prod.name_ta or "").strip():
            return prod.name_ta.strip()
        return (prod.name_en or "").strip()

    prod.get_display_name = _get_display_name
    return prod


@pytest.fixture
def dialog(qapp):
    dlg = LabelPrintDialog()
    dlg.show()
    yield dlg
    dlg.deleteLater()


class TestLabelPrintDialogUI:
    """Test suite for LabelPrintDialog layout, preview and interactions (#819)."""

    def test_format_controls_present_and_options(self, dialog):
        """Format row has Language and Size selectors with all required choices."""
        assert dialog.combo_language is not None
        assert dialog.combo_size is not None

        # 5 language options
        assert dialog.combo_language.count() == 5
        lang_keys = [dialog.combo_language.itemData(i) for i in range(dialog.combo_language.count())]
        assert "en" in lang_keys
        assert "si" in lang_keys
        assert "ta" in lang_keys
        assert "en+si" in lang_keys
        assert "en+ta" in lang_keys

        # Presets: 50x30, 40x25, 58mm, custom
        assert dialog.combo_size.count() == 4
        size_keys = [dialog.combo_size.itemData(i) for i in range(dialog.combo_size.count())]
        assert "50x30" in size_keys
        assert "40x25" in size_keys
        assert "58mm" in size_keys
        assert "custom" in size_keys

    def test_custom_controls_visibility(self, dialog):
        """Custom width/height controls appear only when Custom preset is selected."""
        idx_50 = dialog.combo_size.findData("50x30")
        dialog.combo_size.setCurrentIndex(idx_50)
        assert dialog.custom_dim_widget.isVisible() is False

        idx_custom = dialog.combo_size.findData("custom")
        dialog.combo_size.setCurrentIndex(idx_custom)
        assert dialog.custom_dim_widget.isVisible() is True

        idx_40 = dialog.combo_size.findData("40x25")
        dialog.combo_size.setCurrentIndex(idx_40)
        assert dialog.custom_dim_widget.isVisible() is False

    def test_empty_state_when_queue_empty(self, dialog):
        """When queue is empty, live preview shows helpful empty state."""
        dialog.label_items.clear()
        dialog._refresh_table()
        assert dialog.label_card.isVisible() is False
        assert dialog.empty_preview_widget.isVisible() is True
        assert dialog.btn_print.isEnabled() is False

    def test_live_preview_updates_on_product_selection(self, dialog):
        """Live preview reflects the currently selected product in the queue."""
        p1 = _make_dummy_product(name_en="Prod 1", barcode="111111111111")
        p2 = _make_dummy_product(name_en="Prod 2", barcode="222222222222")

        dialog.label_items = [{"product": p1, "quantity": 1}, {"product": p2, "quantity": 2}]
        dialog._refresh_table()

        dialog.table.selectRow(0)
        assert dialog.label_card.isVisible() is True
        assert dialog.empty_preview_widget.isVisible() is False
        assert dialog.label_card._layout.product_name == "Prod 1"

        dialog.table.selectRow(1)
        assert dialog.label_card._layout.product_name == "Prod 2"

    def test_preview_updates_without_mutating_saved_printer_settings(self, dialog, monkeypatch):
        """Previewing different label sizes does not mutate saved paper_width."""
        saved_width = ConfigService.get("paper_width") or "80mm"
        idx_58 = dialog.combo_size.findData("58mm")
        dialog.combo_size.setCurrentIndex(idx_58)

        # Config remains untouched
        current_width = ConfigService.get("paper_width") or "80mm"
        assert current_width == saved_width

    def test_fallback_warning_visibility(self, dialog):
        """Visible warning is displayed when local name is missing, hidden when present."""
        prod_with_si = _make_dummy_product(name_en="Tea", name_si="තේ")
        prod_no_si = _make_dummy_product(name_en="Coffee", name_si="")

        dialog.label_items = [{"product": prod_with_si, "quantity": 1}]
        dialog._refresh_table()
        dialog.table.selectRow(0)

        # Select Sinhala
        idx_si = dialog.combo_language.findData("si")
        dialog.combo_language.setCurrentIndex(idx_si)
        assert dialog.lbl_fallback_warning.isVisible() is False
        assert dialog.label_card._layout.product_name == "තේ"

        # Switch to product without Sinhala
        dialog.label_items = [{"product": prod_no_si, "quantity": 1}]
        dialog._refresh_table()
        dialog.table.selectRow(0)
        assert dialog.lbl_fallback_warning.isVisible() is True
        assert "Local name unavailable" in dialog.lbl_fallback_warning.text()
        assert dialog.label_card._layout.product_name == "Coffee"

    def test_dimension_validation_disables_print_and_shows_error(self, dialog):
        """Over-width custom labels fail validation, show translated error and disable print."""
        p = _make_dummy_product()
        dialog.label_items = [{"product": p, "quantity": 1}]
        dialog._refresh_table()
        dialog.table.selectRow(0)

        idx_custom = dialog.combo_size.findData("custom")
        dialog.combo_size.setCurrentIndex(idx_custom)

        # Set valid custom size
        dialog.input_width.setText("60")
        dialog.input_height.setText("35")
        assert dialog.btn_print.isEnabled() is True
        assert dialog.lbl_dimension_error.isVisible() is False

        # Set over-width size (e.g. 95 mm when printer is 80mm)
        dialog.input_width.setText("95")
        assert dialog.btn_print.isEnabled() is False
        assert dialog.lbl_dimension_error.isVisible() is True

        # Restore valid size
        dialog.input_width.setText("50")
        assert dialog.btn_print.isEnabled() is True
        assert dialog.lbl_dimension_error.isVisible() is False

    def test_keyboard_shortcuts(self, dialog):
        """Ctrl+P triggers print and Enter adds product."""
        # Enter in search input
        dialog.search_input.setText("test")
        with patch.object(dialog, "_add_product") as mock_add:
            dialog.search_input.returnPressed.emit()
            mock_add.assert_called_once()

        # Ctrl+P shortcut exists on btn_print
        assert dialog.btn_print.shortcut().toString() in ("Ctrl+P", "Ctrl+p")

    def test_print_controls_restore_on_success_and_failure(self, dialog):
        """Print button restores enabled state when print job succeeds or fails."""
        p = _make_dummy_product()
        dialog.label_items = [{"product": p, "quantity": 1}]
        dialog._refresh_table()
        dialog.table.selectRow(0)

        with (
            patch.object(PrintWorker, "add_job", return_value="job_test_1"),
            patch("cbpos.ui.dialogs.label_print_dialog.QMessageBox"),
        ):
            dialog._print_labels()
            assert dialog.btn_print.isEnabled() is False

            # Signal success
            PrintWorker.instance().job_result.emit("job_test_1", True, "")
            assert dialog.btn_print.isEnabled() is True

            # Trigger again and signal failure
            dialog._print_labels()
            assert dialog.btn_print.isEnabled() is False
            PrintWorker.instance().job_result.emit("job_test_1", False, "Connection error")
            assert dialog.btn_print.isEnabled() is True
