"""UI tests for SerialEntryDialog (#823)."""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt

from cbpos.ui.dialogs.serial_entry_dialog import SerialEntryDialog

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def mock_active_warranties():
    with patch(
        "cbpos.core.services.warranty_service.WarrantyService.find_active_warranties_by_serials",
        return_value={},
    ) as m:
        yield m


def _make_product(name_en: str = "Samsung Galaxy S24", serial_mode: str = "REQUIRED"):
    prod = MagicMock()
    prod.id = 42
    prod.name_en = name_en
    prod.name_si = None
    prod.name_ta = None
    prod.serial_mode = serial_mode
    prod.get_display_name = lambda lang=None: name_en
    return prod


class TestSerialEntryDialogUI:
    def test_dialog_initialization_required_mode(self, qtbot):
        product = _make_product(serial_mode="REQUIRED")
        dlg = SerialEntryDialog(product=product, unit_count=2, serial_mode="REQUIRED")
        qtbot.addWidget(dlg)

        assert len(dlg._line_edits) == 2
        assert dlg.btn_skip is None  # Skip hidden for REQUIRED
        assert dlg.btn_confirm is not None
        assert dlg.btn_cancel is not None
        assert dlg.accepts_scans is True

    def test_dialog_initialization_optional_mode(self, qtbot):
        product = _make_product(serial_mode="OPTIONAL")
        dlg = SerialEntryDialog(product=product, unit_count=2, serial_mode="OPTIONAL")
        qtbot.addWidget(dlg)
        dlg.show()

        assert len(dlg._line_edits) == 2
        assert dlg.btn_skip is not None  # Skip visible for OPTIONAL
        assert dlg.btn_skip.isVisible()

    def test_skip_button_returns_none_slots(self, qtbot):
        product = _make_product(serial_mode="OPTIONAL")
        dlg = SerialEntryDialog(product=product, unit_count=3, serial_mode="OPTIONAL")
        qtbot.addWidget(dlg)
        dlg.show()

        with qtbot.waitSignal(dlg.accepted, timeout=1000):
            dlg.btn_skip.click()

        assert dlg.get_serials() == [None, None, None]

    def test_process_barcode_external_hardware_scan(self, qtbot):
        product = _make_product()
        dlg = SerialEntryDialog(product=product, unit_count=2, serial_mode="REQUIRED")
        qtbot.addWidget(dlg)
        dlg.show()

        # First scan fills first input and moves focus to second
        res1 = dlg.process_barcode_external("SN10001")
        assert res1 is True
        assert dlg._line_edits[0].text() == "SN10001"
        assert dlg.focusWidget() is dlg._line_edits[1]

        # Second scan fills second input
        res2 = dlg.process_barcode_external("SN10002")
        assert res2 is True
        assert dlg._line_edits[1].text() == "SN10002"
        assert dlg.get_serials() == ["SN10001", "SN10002"]

    def test_keyboard_enter_advances_focus(self, qtbot):
        product = _make_product()
        dlg = SerialEntryDialog(product=product, unit_count=2, serial_mode="REQUIRED")
        qtbot.addWidget(dlg)
        dlg.show()

        dlg._line_edits[0].setFocus()
        qtbot.keyClicks(dlg._line_edits[0], "ABC12345")
        qtbot.keyClick(dlg._line_edits[0], Qt.Key.Key_Return)

        # Focus should advance to input 1
        assert dlg.focusWidget() is dlg._line_edits[1]

    def test_required_validation_blocks_empty(self, qtbot):
        product = _make_product(serial_mode="REQUIRED")
        dlg = SerialEntryDialog(product=product, unit_count=2, serial_mode="REQUIRED")
        qtbot.addWidget(dlg)

        # Enter only one serial
        dlg._line_edits[0].setText("SER1")
        dlg._on_confirm()

        # Dialog should not have accepted
        assert dlg.result() != dlg.DialogCode.Accepted
        assert "required" in dlg._error_labels[1].text().lower()

    def test_duplicate_in_dialog_validation(self, qtbot):
        product = _make_product()
        dlg = SerialEntryDialog(product=product, unit_count=2, serial_mode="REQUIRED")
        qtbot.addWidget(dlg)

        dlg._line_edits[0].setText("SAME-SERIAL")
        dlg._line_edits[1].setText("SAME-SERIAL")
        dlg._validate_field(0)
        dlg._validate_field(1)

        assert "duplicate" in dlg._error_labels[1].text().lower()
        dlg._on_confirm()
        assert dlg.result() != dlg.DialogCode.Accepted

    def test_duplicate_in_cart_validation(self, qtbot):
        product = _make_product()
        external_cart = {"ALREADY-IN-CART"}
        dlg = SerialEntryDialog(
            product=product,
            unit_count=1,
            serial_mode="REQUIRED",
            external_cart_serials=external_cart,
        )
        qtbot.addWidget(dlg)

        dlg._line_edits[0].setText("ALREADY-IN-CART")
        dlg._validate_field(0)

        assert "cart" in dlg._error_labels[0].text().lower()
        dlg._on_confirm()
        assert dlg.result() != dlg.DialogCode.Accepted

    def test_imei_luhn_advisory_does_not_block_confirm(self, qtbot):
        product = _make_product()
        dlg = SerialEntryDialog(product=product, unit_count=1, serial_mode="REQUIRED")
        qtbot.addWidget(dlg)

        # 15 digits with invalid check digit
        bad_imei = "358765091234560"
        dlg._line_edits[0].setText(bad_imei)
        dlg._validate_field(0, show_warnings=True)

        # Warning is displayed in advisory label
        assert "luhn" in dlg._warning_labels[0].text().lower() or "imei" in dlg._warning_labels[0].text().lower()
        # But confirm still succeeds because it's advisory
        dlg._on_confirm()
        assert dlg.result() == dlg.DialogCode.Accepted
        assert dlg.get_serials() == [bad_imei]

    def test_active_warranty_warning_advisory(self, qtbot):
        product = _make_product()
        dlg = SerialEntryDialog(product=product, unit_count=1, serial_mode="REQUIRED")
        qtbot.addWidget(dlg)

        with patch(
            "cbpos.core.services.warranty_service.WarrantyService.find_active_warranties_by_serials"
        ) as mock_find:
            mock_find.return_value = {"TEST-SN": "WAR-9999"}
            dlg._line_edits[0].setText("TEST-SN")
            dlg._validate_field(0, show_warnings=True)

            assert "WAR-9999" in dlg._warning_labels[0].text()
            dlg._on_confirm()
            assert dlg.result() == dlg.DialogCode.Accepted
            assert dlg.get_serials() == ["TEST-SN"]

    def test_prefills_existing_serials(self, qtbot):
        product = _make_product()
        dlg = SerialEntryDialog(
            product=product,
            unit_count=2,
            serial_mode="REQUIRED",
            existing_serials=["SN01", None],
        )
        qtbot.addWidget(dlg)

        assert dlg._line_edits[0].text() == "SN01"
        assert dlg._line_edits[1].text() == ""
