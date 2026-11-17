"""UI tests for WarrantyLookupDialog and WarrantyCorrectionDialog (#825)."""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from cbpos.core.services.warranty_dto import WarrantyDTO
from cbpos.ui.dialogs.warranty_correction_dialog import WarrantyCorrectionDialog
from cbpos.ui.dialogs.warranty_lookup_dialog import WarrantyLookupDialog


@pytest.fixture
def sample_dto():
    return WarrantyDTO(
        id=101,
        code="INV-2026-00010-01",
        serial_number="IMEI864209012345678",
        product_id=1,
        product_name="Smartphone A15",
        customer_id=1,
        customer_name="Sunil Perera",
        customer_phone="0771234567",
        sale_id=10,
        sale_document_number="INV-2026-00010",
        sold_date=datetime(2026, 1, 15, 10, 30),
        start_date=date(2026, 1, 15),
        end_date=date(2027, 1, 15),
        duration=12,
        duration_unit="MONTHS",
        warranty_type="SHOP",
        remedy="REPAIR_OR_REPLACE",
        terms_snapshot="Standard coverage terms",
        exclusions_snapshot="Liquid or physical damage",
        status="ACTIVE",
        effective_status="ACTIVE",
        days_remaining=240,
        has_active_claim=False,
        active_claim_id=None,
    )


class TestWarrantyLookupDialog:
    def test_lookup_dialog_init(self, qtbot):
        dialog = WarrantyLookupDialog()
        qtbot.addWidget(dialog)

        assert dialog.windowTitle() != ""
        assert dialog.search_input is not None
        assert dialog.table.columnCount() == 6
        assert dialog.detail_content.isHidden()
        assert not dialog.lbl_empty_detail.isHidden()
        assert dialog.btn_start_claim.isEnabled() is False

    def test_lookup_dialog_search_and_populate(self, qtbot, sample_dto):
        dialog = WarrantyLookupDialog()
        qtbot.addWidget(dialog)

        with patch("cbpos.core.services.warranty_service.WarrantyService.search", return_value=[sample_dto]):
            dialog.search_input.setText("Smartphone")
            dialog._do_search()

            assert dialog.table.rowCount() == 1
            assert dialog.table.item(0, 0).text() == "Smartphone A15"
            assert dialog.table.item(0, 1).text() == "IMEI864209012345678"
            assert "Sunil" in dialog.table.item(0, 2).text()

            # Selection displays details
            dialog.table.selectRow(0)
            assert not dialog.detail_content.isHidden()
            assert dialog.lbl_detail_code.text() == "INV-2026-00010-01"
            assert dialog.lbl_val_product.text() == "Smartphone A15"
            assert dialog.txt_terms.toPlainText() == "Standard coverage terms"

    def test_lookup_dialog_barcode_external(self, qtbot, sample_dto):
        dialog = WarrantyLookupDialog()
        qtbot.addWidget(dialog)

        with patch(
            "cbpos.core.services.warranty_service.WarrantyService.search", return_value=[sample_dto]
        ) as mock_search:
            dialog.process_barcode_external("IMEI864209012345678")
            assert dialog.search_input.text() == "IMEI864209012345678"
            mock_search.assert_called_once_with("IMEI864209012345678")


class TestWarrantyCorrectionDialog:
    def test_correction_dialog_validation(self, qtbot, sample_dto):
        dialog = WarrantyCorrectionDialog(sample_dto, user_id=1)
        qtbot.addWidget(dialog)

        # Reason initially empty -> Save disabled
        assert dialog.btn_save.isEnabled() is False

        # Typing whitespace still disabled
        dialog.txt_reason.setPlainText("   ")
        assert dialog.btn_save.isEnabled() is False

        # Typing valid reason enables save
        dialog.txt_reason.setPlainText("Corrected serial entered incorrectly")
        assert dialog.btn_save.isEnabled() is True

    def test_correction_dialog_save_calls_service(self, qtbot, sample_dto):
        dialog = WarrantyCorrectionDialog(sample_dto, user_id=1)
        qtbot.addWidget(dialog)

        dialog.txt_reason.setPlainText("Replaced unit under warranty")
        dialog.txt_serial.setText("NEW-SERIAL-123")

        with patch(
            "cbpos.core.services.warranty_service.WarrantyService.update_warranty_admin", return_value=sample_dto
        ) as mock_update:
            dialog._on_save()
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert call_kwargs["warranty_id"] == 101
            assert call_kwargs["user_id"] == 1
            assert call_kwargs["reason"] == "Replaced unit under warranty"
            assert call_kwargs["serial_number"] == "NEW-SERIAL-123"
