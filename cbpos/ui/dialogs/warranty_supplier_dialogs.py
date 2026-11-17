"""Supplier RMA workflow dialogs (#828, #820).

Contains dialogs for:
- Dispatching item to supplier (WarrantySupplierDispatchDialog)
- Receiving item back from supplier (WarrantySupplierReceiveDialog)
- Recording final supplier outcome (WarrantySupplierOutcomeDialog)
"""

import logging
import threading
from decimal import Decimal

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.services.warranty_claim_receipt_builder import WarrantyClaimReceiptBuilder
from cbpos.core.services.warranty_claim_service import WarrantyClaimService
from cbpos.core.services.warranty_dto import WarrantyClaimDTO
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class WarrantySupplierDispatchDialog(QDialog):
    """Dialog to dispatch defective unit to supplier for RMA (#828)."""

    def __init__(self, claim: WarrantyClaimDTO, user_id: int | None = None, parent=None):
        super().__init__(parent)
        self.claim = claim
        self._user_id = user_id
        self.updated_claim: WarrantyClaimDTO | None = None

        self.setObjectName("WarrantySupplierDispatchDialog")
        self.setWindowTitle(_t("warranty_claim.supplier_dispatch_title", default="Send Claim to Supplier (RMA)"))
        self.setMinimumWidth(500)
        install_wheel_guard(self)
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize supplier dispatch form controls, notes, and actions."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        # Claim info
        lbl_info = QLabel(f"{self.claim.document_number} — {self.claim.product_name}")
        lbl_info.setStyleSheet("font-weight: bold;")
        form.addRow(_t("warranty_claim.claim_no", default="Claim No") + ":", lbl_info)

        if self.claim.item_serial:
            lbl_sn = QLabel(self.claim.item_serial)
            form.addRow(_t("warranty.serial_number", default="Serial") + ":", lbl_sn)

        # Supplier selector
        self.cmb_supplier = QComboBox()
        self._load_suppliers()
        form.addRow(_t("warranty_claim.supplier_select", default="Supplier") + "*:", self.cmb_supplier)

        # RMA Ref / Courier Waybill
        self.txt_rma_ref = QLineEdit()
        self.txt_rma_ref.setPlaceholderText(
            _t("warranty_claim.supplier_rma_ref_placeholder", default="e.g. RMA-99882 or Courier tracking #")
        )
        form.addRow(_t("warranty_claim.supplier_rma_ref", default="Supplier RMA Ref / Waybill") + ":", self.txt_rma_ref)

        # Dispatch Notes
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText(
            _t(
                "warranty_claim.dispatch_notes_placeholder",
                default="Courier service, contact person, or shipping notes...",
            )
        )
        self.txt_notes.setFixedHeight(70)
        form.addRow(_t("notes", default="Notes") + ":", self.txt_notes)

        # Print checkbox
        self.chk_print = QCheckBox(
            _t("warranty_claim.chk_print_dispatch_slip", default="Print thermal RMA dispatch slip on submit")
        )
        self.chk_print.setChecked(True)
        form.addRow("", self.chk_print)

        layout.addLayout(form)

        # PDF Export button
        row_pdf = QHBoxLayout()
        self.btn_export_pdf = QPushButton(_t("warranty_claim.btn_supplier_pdf", default="Save RMA Waybill PDF"))
        self.btn_export_pdf.setIcon(Icons.get(Icons.PRINT))
        self.btn_export_pdf.clicked.connect(self._on_export_pdf)
        row_pdf.addWidget(self.btn_export_pdf)
        row_pdf.addStretch()
        layout.addLayout(row_pdf)

        # Footer
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="warranty_claim.btn_supplier_dispatch",
            on_primary=self._on_save,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnDispatchSupplier",
        )
        layout.addLayout(footer_layout)

    def _load_suppliers(self) -> None:
        try:
            suppliers = SupplierService.get_all_suppliers(active_only=True)
            self.cmb_supplier.clear()
            selected_idx = 0
            for idx, s in enumerate(suppliers):
                self.cmb_supplier.addItem(s.company_name, s.id)
                if self.claim.supplier_id and s.id == self.claim.supplier_id:
                    selected_idx = idx
            if suppliers:
                self.cmb_supplier.setCurrentIndex(selected_idx)
        except Exception as e:
            logger.error("Failed to load suppliers: %s", e)

    def _on_export_pdf(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            _t("warranty_claim.save_rma_pdf_title", default="Save Supplier RMA PDF"),
            f"RMA-{self.claim.document_number}.pdf",
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return

        supplier_id = self.cmb_supplier.currentData()
        supplier_name = self.cmb_supplier.currentText()
        rma_ref = self.txt_rma_ref.text().strip() or None

        export_dto = WarrantyClaimDTO(
            **{
                **self.claim.__dict__,
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "supplier_rma_ref": rma_ref,
            }
        )

        def _generate():
            try:
                WarrantyClaimReceiptBuilder.build_supplier_dispatch_pdf(export_dto, file_path)
            except Exception as e:
                logger.error("Failed to generate RMA PDF: %s", e)

        threading.Thread(target=_generate, daemon=True).start()
        QMessageBox.information(
            self,
            _t("common.success", default="Success"),
            _t("warranty_claim.pdf_saved", default="RMA Waybill PDF saved successfully"),
        )

    def _on_save(self) -> None:
        supplier_id = self.cmb_supplier.currentData()
        if not supplier_id:
            QMessageBox.warning(
                self,
                _t("common.error", default="Error"),
                _t("warranty_claim.select_supplier", default="Please select a supplier"),
            )
            return

        actor_id = self._user_id
        if actor_id is None:
            curr = AuthService.get_current_user()
            if curr:
                actor_id = curr.id

        if actor_id is None:
            QMessageBox.critical(
                self,
                _t("common.error", default="Error"),
                _t("errors.unauthorized", default="No authenticated user session"),
            )
            return

        rma_ref = self.txt_rma_ref.text().strip() or None
        notes = self.txt_notes.toPlainText().strip() or None

        try:
            dto = WarrantyClaimService.send_to_supplier(
                claim_id=self.claim.id,
                supplier_id=int(supplier_id),
                user_id=actor_id,
                supplier_rma_ref=rma_ref,
                notes=notes,
            )
            self.updated_claim = dto

            if self.chk_print.isChecked():
                try:
                    commands = WarrantyClaimReceiptBuilder.build_supplier_dispatch_receipt(dto)
                    PrintWorker.instance().add_job("print_commands", commands)
                except Exception as ex:
                    logger.warning("Failed to print supplier dispatch slip: %s", ex)

            QMessageBox.information(
                self,
                _t("common.success", default="Success"),
                _t(
                    "warranty_claim.dispatched_success",
                    default=f"Claim {dto.document_number} dispatched to supplier",
                    number=dto.document_number,
                ),
            )
            self.accept()
        except Exception as e:
            logger.error("Error dispatching claim: %s", e)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))


class WarrantySupplierReceiveDialog(QDialog):
    """Dialog to receive item back from supplier/service center (#828)."""

    def __init__(self, claim: WarrantyClaimDTO, user_id: int | None = None, parent=None):
        super().__init__(parent)
        self.claim = claim
        self._user_id = user_id
        self.updated_claim: WarrantyClaimDTO | None = None

        self.setObjectName("WarrantySupplierReceiveDialog")
        self.setWindowTitle(_t("warranty_claim.supplier_return_title", default="Receive from Supplier (RMA)"))
        self.setMinimumWidth(480)
        install_wheel_guard(self)
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize supplier receive form controls and notes."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        lbl_info = QLabel(f"{self.claim.document_number} — {self.claim.product_name}")
        lbl_info.setStyleSheet("font-weight: bold;")
        form.addRow(_t("warranty_claim.claim_no", default="Claim No") + ":", lbl_info)

        if self.claim.supplier_name:
            form.addRow(
                _t("warranty_claim.supplier_select", default="Supplier") + ":", QLabel(self.claim.supplier_name)
            )

        # Status choice
        self.cmb_status = QComboBox()
        self.cmb_status.addItem(
            _t("warranty_claim.status_supplier_returned", default="Supplier Returned"), "SUPPLIER_RETURNED"
        )
        self.cmb_status.addItem(
            _t("warranty_claim.status_in_inspection", default="Return to Inspection"), "IN_INSPECTION"
        )
        form.addRow(_t("status", default="Status") + ":", self.cmb_status)

        # Notes
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText(
            _t(
                "warranty_claim.receive_notes_placeholder",
                default="Condition of received item, courier details, etc...",
            )
        )
        self.txt_notes.setFixedHeight(80)
        form.addRow(_t("notes", default="Notes") + ":", self.txt_notes)

        layout.addLayout(form)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="warranty_claim.btn_receive",
            on_primary=self._on_save,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnReceiveSupplier",
        )
        layout.addLayout(footer_layout)

    def _on_save(self) -> None:
        actor_id = self._user_id
        if actor_id is None:
            curr = AuthService.get_current_user()
            if curr:
                actor_id = curr.id

        if actor_id is None:
            QMessageBox.critical(
                self,
                _t("common.error", default="Error"),
                _t("errors.unauthorized", default="No authenticated user session"),
            )
            return

        to_status = self.cmb_status.currentData()
        notes = self.txt_notes.toPlainText().strip() or None

        try:
            dto = WarrantyClaimService.receive_from_supplier(
                claim_id=self.claim.id,
                user_id=actor_id,
                to_status=to_status,
                notes=notes,
            )
            self.updated_claim = dto
            QMessageBox.information(
                self,
                _t("common.success", default="Success"),
                _t("warranty_claim.received_success", default="Item received back from supplier successfully"),
            )
            self.accept()
        except Exception as e:
            logger.error("Error receiving from supplier: %s", e)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))


class WarrantySupplierOutcomeDialog(QDialog):
    """Dialog to record final supplier outcome and credit notes (#828)."""

    def __init__(self, claim: WarrantyClaimDTO, user_id: int | None = None, parent=None):
        super().__init__(parent)
        self.claim = claim
        self._user_id = user_id
        self.updated_claim: WarrantyClaimDTO | None = None

        self.setObjectName("WarrantySupplierOutcomeDialog")
        self.setWindowTitle(_t("warranty_claim.supplier_outcome_title", default="Record Supplier RMA Outcome"))
        self.setMinimumWidth(500)
        install_wheel_guard(self)
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize supplier outcome options, inputs, and footer."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        lbl_info = QLabel(f"{self.claim.document_number} — {self.claim.product_name}")
        lbl_info.setStyleSheet("font-weight: bold;")
        form.addRow(_t("warranty_claim.claim_no", default="Claim No") + ":", lbl_info)

        if self.claim.supplier_name:
            form.addRow(
                _t("warranty_claim.supplier_select", default="Supplier") + ":", QLabel(self.claim.supplier_name)
            )

        # Outcome combo
        self.cmb_outcome = QComboBox()
        self.cmb_outcome.addItem(_t("warranty_claim.outcome_repaired", default="Repaired by Supplier"), "REPAIRED")
        self.cmb_outcome.addItem(_t("warranty_claim.outcome_replaced", default="Replaced by Supplier"), "REPLACED")
        self.cmb_outcome.addItem(
            _t("warranty_claim.outcome_credit_note", default="Supplier Credit Note"), "CREDIT_NOTE"
        )
        self.cmb_outcome.addItem(_t("warranty_claim.outcome_rejected", default="Rejected by Supplier"), "REJECTED")
        self.cmb_outcome.currentIndexChanged.connect(self._on_outcome_changed)
        form.addRow(_t("warranty_claim.supplier_outcome", default="Supplier Outcome") + "*:", self.cmb_outcome)

        # Replacement Serial
        self.txt_replacement_serial = QLineEdit()
        self.txt_replacement_serial.setPlaceholderText(
            _t("warranty_claim.replacement_serial_placeholder", default="Replacement serial/IMEI")
        )
        self.lbl_replacement_serial = QLabel(
            _t("warranty_claim.replacement_serial", default="Replacement Serial") + ":"
        )
        self.lbl_replacement_serial.setVisible(False)
        self.txt_replacement_serial.setVisible(False)
        form.addRow(self.lbl_replacement_serial, self.txt_replacement_serial)

        # Credit note amount
        self.spn_credit_amount = QDoubleSpinBox()
        self.spn_credit_amount.setRange(0.01, 9999999.99)
        self.spn_credit_amount.setDecimals(2)
        self.spn_credit_amount.setValue(0.00)
        self.lbl_credit_amount = QLabel(
            _t("warranty_claim.supplier_credit_amount", default="Supplier Credit Amount") + "*:"
        )
        self.lbl_credit_amount.setVisible(False)
        self.spn_credit_amount.setVisible(False)
        form.addRow(self.lbl_credit_amount, self.spn_credit_amount)

        # Notes
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText(
            _t(
                "warranty_claim.outcome_notes_placeholder",
                default="Supplier repair summary, credit note reference, or rejection details...",
            )
        )
        self.txt_notes.setFixedHeight(80)
        form.addRow(_t("notes", default="Notes") + ":", self.txt_notes)

        layout.addLayout(form)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self._on_save,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnSaveSupplierOutcome",
        )
        layout.addLayout(footer_layout)

    def _on_outcome_changed(self) -> None:
        outcome = self.cmb_outcome.currentData()
        is_replaced = outcome == "REPLACED"
        is_credit = outcome == "CREDIT_NOTE"

        self.lbl_replacement_serial.setVisible(is_replaced)
        self.txt_replacement_serial.setVisible(is_replaced)

        self.lbl_credit_amount.setVisible(is_credit)
        self.spn_credit_amount.setVisible(is_credit)

    def _on_save(self) -> None:
        actor_id = self._user_id
        if actor_id is None:
            curr = AuthService.get_current_user()
            if curr:
                actor_id = curr.id

        if actor_id is None:
            QMessageBox.critical(
                self,
                _t("common.error", default="Error"),
                _t("errors.unauthorized", default="No authenticated user session"),
            )
            return

        outcome = self.cmb_outcome.currentData()
        credit = Decimal(str(self.spn_credit_amount.value())) if outcome == "CREDIT_NOTE" else Decimal("0.00")
        rep_sn = self.txt_replacement_serial.text().strip().upper() if outcome == "REPLACED" else None
        notes = self.txt_notes.toPlainText().strip() or None

        if outcome == "CREDIT_NOTE" and credit <= Decimal("0.00"):
            QMessageBox.warning(
                self,
                _t("common.error", default="Error"),
                _t("warranty_claim.credit_amount_required", default="Please enter a valid credit amount"),
            )
            return

        try:
            dto = WarrantyClaimService.record_supplier_outcome(
                claim_id=self.claim.id,
                outcome=outcome,
                user_id=actor_id,
                credit_amount=credit,
                replacement_serial=rep_sn,
                notes=notes,
            )
            self.updated_claim = dto
            QMessageBox.information(
                self,
                _t("common.success", default="Success"),
                _t("warranty_claim.outcome_recorded_success", default="Supplier outcome recorded successfully"),
            )
            self.accept()
        except Exception as e:
            logger.error("Error recording supplier outcome: %s", e)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))
