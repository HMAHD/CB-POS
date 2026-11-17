"""UI tests for Warranty Claims workflow dialogs and board (#826, #820)."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QDialog

from cbpos.core.services.warranty_dto import WarrantyClaimDTO, WarrantyClaimEventDTO, WarrantyDTO
from cbpos.ui.dialogs.warranty_claim_intake_dialog import WarrantyClaimIntakeDialog
from cbpos.ui.dialogs.warranty_claim_resolve_dialog import WarrantyClaimResolveDialog
from cbpos.ui.dialogs.warranty_lookup_dialog import WarrantyLookupDialog
from cbpos.ui.views.warranty_claims_board_view import WarrantyClaimsBoardDialog, WarrantyClaimsBoardView


@pytest.fixture
def sample_warranty_dto():
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


@pytest.fixture
def sample_claim_dto():
    ev1 = WarrantyClaimEventDTO(
        id=1,
        claim_id=201,
        from_status=None,
        to_status="INTAKE",
        user_id=2,
        username="cashier1",
        event_time=datetime(2026, 2, 1, 10, 0),
        notes="Claim intake registered",
    )
    return WarrantyClaimDTO(
        id=201,
        document_number="WC-2026-00001",
        warranty_id=101,
        warranty_code="INV-2026-00010-01",
        product_id=1,
        product_name="Smartphone A15",
        customer_id=1,
        customer_name="Sunil Perera",
        customer_phone="0771234567",
        item_serial="IMEI864209012345678",
        claim_status="INTAKE",
        intake_date=datetime(2026, 2, 1, 10, 0),
        defect_description="Battery draining extremely fast and overheating",
        item_condition="Scratches on corners",
        accessories_received="Charger and cable",
        is_covered=True,
        resolution=None,
        resolution_notes=None,
        rejection_reason=None,
        replacement_warranty_id=None,
        replacement_serial=None,
        repair_cost=Decimal("0.00"),
        charge_customer=Decimal("0.00"),
        resolved_by_user_id=None,
        resolved_by_username=None,
        resolved_at=None,
        collected_by_name=None,
        collected_at=None,
        user_id=2,
        created_at=datetime(2026, 2, 1, 10, 0),
        events=(ev1,),
    )


class TestWarrantyClaimIntakeDialog:
    def test_intake_dialog_prepopulates_from_warranty(self, qtbot, sample_warranty_dto):
        dialog = WarrantyClaimIntakeDialog(warranty=sample_warranty_dto)
        qtbot.addWidget(dialog)

        assert dialog.txt_customer_name.text() == "Sunil Perera"
        assert dialog.txt_customer_phone.text() == "0771234567"
        assert dialog.txt_serial.text() == "IMEI864209012345678"
        assert dialog.chk_covered.isChecked() is True
        assert dialog.chk_print_slip.isChecked() is True

    def test_intake_dialog_validation_defect_required(self, qtbot, sample_warranty_dto):
        dialog = WarrantyClaimIntakeDialog(warranty=sample_warranty_dto)
        qtbot.addWidget(dialog)

        dialog.txt_defect.setText("")
        with patch("cbpos.ui.dialogs.warranty_claim_intake_dialog.QMessageBox.warning") as mock_warn:
            dialog._on_save()
            assert mock_warn.called

        assert dialog.created_claim is None
        assert dialog.result() != QDialog.DialogCode.Accepted

    def test_intake_dialog_successful_submission(self, qtbot, sample_warranty_dto, sample_claim_dto):
        dialog = WarrantyClaimIntakeDialog(warranty=sample_warranty_dto, user_id=2)
        qtbot.addWidget(dialog)

        dialog.txt_defect.setText("Speaker crackling")
        dialog.chk_print_slip.setChecked(False)

        with (
            patch(
                "cbpos.core.services.warranty_claim_service.WarrantyClaimService.create_claim",
                return_value=sample_claim_dto,
            ),
            patch("cbpos.ui.dialogs.warranty_claim_intake_dialog.QMessageBox.information"),
        ):
            dialog._on_save()

        assert dialog.created_claim is not None
        assert dialog.created_claim.document_number == "WC-2026-00001"


class TestWarrantyClaimResolveDialog:
    def test_resolve_dialog_replacement_toggle(self, qtbot, sample_claim_dto):
        dialog = WarrantyClaimResolveDialog(claim=sample_claim_dto)
        qtbot.addWidget(dialog)

        # Initially REPAIRED (default 0 index) -> replacement serial disabled
        assert dialog.txt_replacement_serial.isEnabled() is False
        assert dialog.cmb_replacement_product.isHidden() is True

        # Select REPLACED_SAME
        idx = dialog.cmb_resolution.findData("REPLACED_SAME")
        dialog.cmb_resolution.setCurrentIndex(idx)
        assert dialog.txt_replacement_serial.isEnabled() is True
        assert dialog.cmb_replacement_product.isHidden() is True

        # Select REPLACED_DIFFERENT
        with patch("cbpos.ui.dialogs.warranty_claim_resolve_dialog.ProductService.get_all_products", return_value=[]):
            idx_diff = dialog.cmb_resolution.findData("REPLACED_DIFFERENT")
            dialog.cmb_resolution.setCurrentIndex(idx_diff)
            assert dialog.txt_replacement_serial.isEnabled() is True
            assert dialog.cmb_replacement_product.isHidden() is False
            assert dialog.cmb_replacement_product.isEnabled() is True

        # Switch back to REPAIRED
        idx_rep = dialog.cmb_resolution.findData("REPAIRED")
        dialog.cmb_resolution.setCurrentIndex(idx_rep)
        assert dialog.txt_replacement_serial.isEnabled() is False
        assert dialog.cmb_replacement_product.isHidden() is True

    def test_resolve_dialog_wires_replace_from_stock_on_save(self, qtbot, sample_claim_dto):
        dialog = WarrantyClaimResolveDialog(claim=sample_claim_dto, user_id=2)
        qtbot.addWidget(dialog)

        idx = dialog.cmb_resolution.findData("REPLACED_SAME")
        dialog.cmb_resolution.setCurrentIndex(idx)
        dialog.txt_replacement_serial.setText("NEW-SN-123")

        with (
            patch(
                "cbpos.core.services.warranty_claim_service.WarrantyClaimService.replace_from_stock",
                return_value=sample_claim_dto,
            ) as mock_replace,
            patch("cbpos.ui.dialogs.warranty_claim_resolve_dialog.QMessageBox.information"),
        ):
            dialog._on_save()
            assert mock_replace.called
            assert mock_replace.call_args.kwargs["new_serial"] == "NEW-SN-123"
            assert mock_replace.call_args.kwargs["replacement_product_id"] == sample_claim_dto.product_id

    def test_resolve_dialog_wires_refund_claim_on_save(self, qtbot, sample_claim_dto):
        from cbpos.core.services.refund_service import RefundResult

        mock_refund_res = RefundResult(
            refund_sale_id=99,
            refund_document_number="CN-2026-0001",
            total_refund_amount=Decimal("45000.00"),
            refund_sale=None,
            tenders=[],
        )

        dialog = WarrantyClaimResolveDialog(claim=sample_claim_dto, user_id=2)
        qtbot.addWidget(dialog)

        idx = dialog.cmb_resolution.findData("REFUNDED")
        dialog.cmb_resolution.setCurrentIndex(idx)
        dialog.txt_notes.setText("Unrepairable defect")

        with (
            patch(
                "cbpos.core.services.warranty_claim_service.WarrantyClaimService.refund_claim",
                return_value=(sample_claim_dto, mock_refund_res),
            ) as mock_refund,
            patch("cbpos.ui.dialogs.warranty_claim_resolve_dialog.QMessageBox.information"),
        ):
            dialog._on_save()
            assert mock_refund.called
            assert mock_refund.call_args.kwargs["reason"] == "Unrepairable defect"


class TestWarrantyClaimsBoardView:
    def test_board_view_layout_and_selection(self, qtbot, sample_claim_dto):
        with patch(
            "cbpos.core.services.warranty_claim_service.WarrantyClaimService.list_claims",
            return_value=[sample_claim_dto],
        ):
            view = WarrantyClaimsBoardView()
            qtbot.addWidget(view)

            assert view.table.rowCount() == 1
            assert view.table.item(0, 0).text() == "WC-2026-00001"
            assert view.table.item(0, 5).text() == "Smartphone A15"

            # Select row and verify detail pane
            view.table.selectRow(0)
            assert not view.detail_content.isHidden()
            assert view.lbl_detail_doc.text() == "WC-2026-00001"
            assert "Battery draining" in view.lbl_defect_val.text()

    def test_board_dialog_wrapper(self, qtbot):
        with patch("cbpos.core.services.warranty_claim_service.WarrantyClaimService.list_claims", return_value=[]):
            dialog = WarrantyClaimsBoardDialog()
            qtbot.addWidget(dialog)
            assert dialog.board_view is not None


class TestWarrantyLookupClaimIntegration:
    def test_lookup_dialog_claim_button_enabled_when_no_active_claim(self, qtbot, sample_warranty_dto):
        dialog = WarrantyLookupDialog()
        qtbot.addWidget(dialog)

        with patch("cbpos.core.services.warranty_service.WarrantyService.search", return_value=[sample_warranty_dto]):
            dialog.search_input.setText("Smartphone")
            dialog._do_search()

        assert dialog.btn_start_claim.isEnabled() is True
        assert dialog.btn_start_claim.toolTip() == ""

    def test_lookup_dialog_claim_button_disabled_when_active_claim_exists(self, qtbot, sample_warranty_dto):
        claim_warranty = WarrantyDTO(
            **{**sample_warranty_dto.__dict__, "has_active_claim": True, "active_claim_id": 99}
        )
        dialog = WarrantyLookupDialog()
        qtbot.addWidget(dialog)

        with patch("cbpos.core.services.warranty_service.WarrantyService.search", return_value=[claim_warranty]):
            dialog.search_input.setText("Smartphone")
            dialog._do_search()

        assert dialog.btn_start_claim.isEnabled() is False
        assert dialog.btn_start_claim.toolTip() != ""
