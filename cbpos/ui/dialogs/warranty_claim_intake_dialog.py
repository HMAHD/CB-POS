"""Warranty Claim Intake Dialog (#826, #820)."""

import logging

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.warranty_claim_receipt_builder import WarrantyClaimReceiptBuilder
from cbpos.core.services.warranty_claim_service import WarrantyClaimService
from cbpos.core.services.warranty_dto import WarrantyClaimDTO, WarrantyDTO
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.widgets.dialog_footer import make_dialog_footer

logger = logging.getLogger(__name__)


class WarrantyClaimIntakeDialog(QDialog):
    """Modal dialog allowing staff to register a new warranty claim (#826)."""

    def __init__(
        self,
        warranty: WarrantyDTO | None = None,
        user_id: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.warranty = warranty
        self._user_id = user_id
        self.created_claim: WarrantyClaimDTO | None = None

        self.setObjectName("WarrantyClaimIntakeDialog")
        self.setWindowTitle(_t("warranty_claim.intake_title", default="Register Warranty Claim"))
        self.setMinimumWidth(520)
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize form inputs and dialog controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        # Warranty code header (if linked)
        if self.warranty:
            lbl_code_val = QLabel(f"{self.warranty.code} ({self.warranty.product_name})")
            lbl_code_val.setStyleSheet("font-weight: bold;")
            form.addRow(_t("warranty_lookup.code_label", default="Warranty Code") + ":", lbl_code_val)

        # Customer details
        default_cust = self.warranty.customer_name if self.warranty else ""
        self.txt_customer_name = QLineEdit(default_cust or "")
        self.txt_customer_name.setPlaceholderText(
            _t("warranty_claim.customer_name_placeholder", default="Customer Name")
        )
        form.addRow(_t("customer", default="Customer") + ":", self.txt_customer_name)

        default_phone = self.warranty.customer_phone if self.warranty else ""
        self.txt_customer_phone = QLineEdit(default_phone or "")
        self.txt_customer_phone.setPlaceholderText(
            _t("warranty_claim.customer_phone_placeholder", default="07X XXXXXXX")
        )
        form.addRow(_t("phone", default="Phone") + ":", self.txt_customer_phone)

        # Serial Number
        default_sn = self.warranty.serial_number if self.warranty else ""
        self.txt_serial = QLineEdit(default_sn or "")
        self.txt_serial.setPlaceholderText(_t("warranty_lookup.serial_placeholder", default="Enter serial/IMEI"))
        form.addRow(_t("warranty.serial_number", default="Serial Number") + ":", self.txt_serial)

        # Coverage Status Checkbox
        is_covered_default = True
        if self.warranty:
            is_covered_default = self.warranty.effective_status in ("ACTIVE", "EXPIRING")

        self.chk_covered = QCheckBox(_t("warranty_claim.chk_is_covered", default="Item is under active warranty"))
        self.chk_covered.setChecked(is_covered_default)
        form.addRow(_t("warranty_claim.coverage", default="Coverage") + ":", self.chk_covered)

        # Defect Description (Mandatory)
        self.txt_defect = QTextEdit()
        self.txt_defect.setPlaceholderText(
            _t("warranty_claim.defect_placeholder", default="Describe customer reported fault or defect in detail...")
        )
        self.txt_defect.setFixedHeight(75)
        form.addRow(_t("warranty_claim.defect", default="Defect Description") + "*:", self.txt_defect)

        # Item Condition
        self.txt_condition = QLineEdit()
        self.txt_condition.setPlaceholderText(
            _t("warranty_claim.condition_placeholder", default="e.g. Scratches on screen, normal wear")
        )
        form.addRow(_t("warranty_claim.condition", default="Item Condition") + ":", self.txt_condition)

        # Accessories Received
        self.txt_accessories = QLineEdit()
        self.txt_accessories.setPlaceholderText(
            _t("warranty_claim.accessories_placeholder", default="e.g. Charger, USB cable, box")
        )
        form.addRow(_t("warranty_claim.accessories", default="Accessories Received") + ":", self.txt_accessories)

        # Print slip checkbox
        self.chk_print_slip = QCheckBox(
            _t("warranty_claim.chk_print_slip", default="Print thermal intake slip on creation")
        )
        self.chk_print_slip.setChecked(True)
        form.addRow("", self.chk_print_slip)

        layout.addLayout(form)

        # Dialog Footer
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="warranty_claim.btn_create_claim",
            on_primary=self._on_save,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnCreateClaim",
        )
        layout.addLayout(footer_layout)

    def _on_save(self) -> None:
        """Validate and create the claim."""
        defect = self.txt_defect.toPlainText().strip()
        if not defect:
            QMessageBox.warning(
                self,
                _t("common.error", default="Error"),
                _t("warranty_claim.defect_required", default="Defect description is required"),
            )
            self.txt_defect.setFocus()
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

        warranty_id = self.warranty.id if self.warranty else None
        cust_name = self.txt_customer_name.text().strip() or None
        cust_phone = self.txt_customer_phone.text().strip() or None
        serial = self.txt_serial.text().strip().upper() or None
        condition = self.txt_condition.text().strip() or None
        accessories = self.txt_accessories.text().strip() or None
        is_covered = self.chk_covered.isChecked()

        try:
            dto = WarrantyClaimService.create_claim(
                defect_description=defect,
                user_id=actor_id,
                warranty_id=warranty_id,
                customer_name_snapshot=cust_name,
                customer_phone_snapshot=cust_phone,
                item_serial=serial,
                accessories_received=accessories,
                item_condition=condition,
                is_covered=is_covered,
            )
            self.created_claim = dto

            # Print intake slip if requested
            if self.chk_print_slip.isChecked():
                self._print_intake_slip(dto)

            QMessageBox.information(
                self,
                _t("common.success", default="Success"),
                _t(
                    "warranty_claim.claim_created_success",
                    default=f"Warranty claim {dto.document_number} registered successfully",
                    number=dto.document_number,
                ),
            )
            self.accept()

        except Exception as e:
            logger.error("Error creating warranty claim: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                _t("common.error", default="Error"),
                str(e),
            )

    def _print_intake_slip(self, claim: WarrantyClaimDTO) -> None:
        """Build and send intake slip to PrintWorker asynchronously."""
        try:
            commands = WarrantyClaimReceiptBuilder.build_intake_slip(claim)
            PrintWorker.instance().add_job("print_commands", commands)
        except Exception as e:
            logger.warning("Failed to dispatch intake slip print job: %s", e)
