"""Warranty Claim Resolution Dialog (#826, #820)."""

import logging
from decimal import Decimal

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.warranty_claim_service import WarrantyClaimService
from cbpos.core.services.warranty_dto import WarrantyClaimDTO
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class WarrantyClaimResolveDialog(QDialog):
    """Modal dialog allowing authorized staff to record claim resolution and costs (#826)."""

    def __init__(
        self,
        claim: WarrantyClaimDTO,
        user_id: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.claim = claim
        self._user_id = user_id
        self.resolved_claim: WarrantyClaimDTO | None = None

        self.setObjectName("WarrantyClaimResolveDialog")
        self.setWindowTitle(_t("warranty_claim.resolve_title", default="Resolve Warranty Claim"))
        self.setMinimumWidth(500)
        self.init_ui()
        install_wheel_guard(self)

    def init_ui(self) -> None:
        """Initialize resolution form controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        # Claim header info
        lbl_claim_val = QLabel(f"{self.claim.document_number} — {self.claim.product_name}")
        lbl_claim_val.setStyleSheet("font-weight: bold;")
        form.addRow(_t("warranty_claim.claim_no", default="Claim No") + ":", lbl_claim_val)

        # Resolution type combo
        self.cmb_resolution = QComboBox()
        self.cmb_resolution.addItem(_t("warranty_claim.res_repaired", default="Repaired"), "REPAIRED")
        self.cmb_resolution.addItem(
            _t("warranty_claim.res_replaced_same", default="Replaced (Same Model)"), "REPLACED_SAME"
        )
        self.cmb_resolution.addItem(
            _t("warranty_claim.res_replaced_diff", default="Replaced (Different Model)"), "REPLACED_DIFFERENT"
        )
        self.cmb_resolution.addItem(_t("warranty_claim.res_refunded", default="Refund Approved"), "REFUNDED")
        self.cmb_resolution.addItem(
            _t("warranty_claim.res_rejected", default="Rejected (Uncovered)"), "REJECTED_UNCOVERED"
        )
        self.cmb_resolution.currentIndexChanged.connect(self._on_resolution_changed)
        form.addRow(_t("warranty_claim.resolution", default="Resolution") + "*:", self.cmb_resolution)

        # Replacement Product (active for REPLACED_DIFFERENT)
        self.cmb_replacement_product = QComboBox()
        self.cmb_replacement_product.setEnabled(False)
        self.cmb_replacement_product.setVisible(False)
        self.lbl_replacement_product = QLabel(
            _t("warranty_claim.replacement_product", default="Replacement Product") + "*:"
        )
        self.lbl_replacement_product.setVisible(False)
        form.addRow(self.lbl_replacement_product, self.cmb_replacement_product)

        # Replacement Serial (active for replacements)
        self.txt_replacement_serial = QLineEdit()
        self.txt_replacement_serial.setPlaceholderText(
            _t("warranty_claim.replacement_serial_placeholder", default="Replacement serial/IMEI")
        )
        self.txt_replacement_serial.setEnabled(False)
        form.addRow(
            _t("warranty_claim.replacement_serial", default="Replacement Serial") + ":", self.txt_replacement_serial
        )

        # Repair Cost (Shop Cost)
        self.spn_repair_cost = QDoubleSpinBox()
        self.spn_repair_cost.setRange(0.0, 9999999.99)
        self.spn_repair_cost.setDecimals(2)
        self.spn_repair_cost.setValue(float(self.claim.repair_cost or Decimal("0.00")))
        form.addRow(_t("warranty_claim.repair_cost", default="Repair Cost (Shop)") + ":", self.spn_repair_cost)

        # Customer Charge (e.g. out of warranty or parts)
        self.spn_customer_charge = QDoubleSpinBox()
        self.spn_customer_charge.setRange(0.0, 9999999.99)
        self.spn_customer_charge.setDecimals(2)
        self.spn_customer_charge.setValue(float(self.claim.charge_customer or Decimal("0.00")))
        form.addRow(_t("warranty_claim.customer_charge", default="Customer Charge") + ":", self.spn_customer_charge)

        # Resolution Notes
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText(
            _t(
                "warranty_claim.resolution_notes_placeholder",
                default="Details of repair, parts replaced, or reason for decision...",
            )
        )
        self.txt_notes.setFixedHeight(80)
        form.addRow(_t("notes", default="Resolution Notes") + ":", self.txt_notes)

        layout.addLayout(form)

        # Footer
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="warranty_claim.btn_resolve",
            on_primary=self._on_save,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnResolveClaim",
        )
        layout.addLayout(footer_layout)

    def _load_replacement_products(self) -> None:
        """Populate replacement product dropdown with active products and stock levels."""
        try:
            products = ProductService().get_all_products()
            self.cmb_replacement_product.clear()
            for p in products:
                name = p.name_en or f"Product #{p.id}"
                stock = p.stock_qty or Decimal("0.000")
                self.cmb_replacement_product.addItem(f"{name} (Stock: {stock:g})", p.id)
        except Exception as e:
            logger.error("Failed to load replacement products: %s", e)

    def _on_resolution_changed(self) -> None:
        """Enable or disable replacement serial and product fields based on resolution type."""
        res_data = self.cmb_resolution.currentData()
        is_replacement = res_data in ("REPLACED_SAME", "REPLACED_DIFFERENT")
        self.txt_replacement_serial.setEnabled(is_replacement)
        if not is_replacement:
            self.txt_replacement_serial.clear()

        is_diff = res_data == "REPLACED_DIFFERENT"
        self.lbl_replacement_product.setVisible(is_diff)
        self.cmb_replacement_product.setVisible(is_diff)
        self.cmb_replacement_product.setEnabled(is_diff)
        if is_diff and self.cmb_replacement_product.count() == 0:
            self._load_replacement_products()

    def _on_save(self) -> None:
        """Validate resolution inputs and call service."""
        res_type = self.cmb_resolution.currentData()
        notes = self.txt_notes.toPlainText().strip() or None
        rep_serial = self.txt_replacement_serial.text().strip().upper() or None
        cost = Decimal(str(self.spn_repair_cost.value()))
        charge = Decimal(str(self.spn_customer_charge.value()))

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

        try:
            if res_type == "REPLACED_SAME":
                if not self.claim.product_id:
                    raise ValueError(_t("warranty_claim.missing_claim_product", default="Claim has no linked product"))
                dto = WarrantyClaimService.replace_from_stock(
                    claim_id=self.claim.id,
                    replacement_product_id=self.claim.product_id,
                    user_id=actor_id,
                    new_serial=rep_serial,
                    resolution_notes=notes,
                    repair_cost=cost,
                    charge_customer=charge,
                )
            elif res_type == "REPLACED_DIFFERENT":
                diff_prod_id = self.cmb_replacement_product.currentData()
                if not diff_prod_id:
                    raise ValueError(
                        _t(
                            "warranty_claim.select_replacement_product",
                            default="Please select a replacement product",
                        )
                    )
                dto = WarrantyClaimService.replace_from_stock(
                    claim_id=self.claim.id,
                    replacement_product_id=int(diff_prod_id),
                    user_id=actor_id,
                    new_serial=rep_serial,
                    resolution_notes=notes,
                    repair_cost=cost,
                    charge_customer=charge,
                )
            elif res_type == "REFUNDED":
                dto, _ = WarrantyClaimService.refund_claim(
                    claim_id=self.claim.id,
                    user_id=actor_id,
                    reason=notes,
                )
            else:
                dto = WarrantyClaimService.resolve_claim(
                    claim_id=self.claim.id,
                    resolution=res_type,
                    user_id=actor_id,
                    resolution_notes=notes,
                    repair_cost=cost,
                    charge_customer=charge,
                    replacement_serial=rep_serial,
                )
            self.resolved_claim = dto

            QMessageBox.information(
                self,
                _t("common.success", default="Success"),
                _t(
                    "warranty_claim.claim_resolved_success",
                    default=f"Claim {dto.document_number} resolved as {res_type}",
                    number=dto.document_number,
                    resolution=res_type,
                ),
            )
            self.accept()

        except PermissionError:
            QMessageBox.critical(
                self,
                _t("common.error", default="Error"),
                _t("errors.permission_denied", default="Permission denied"),
            )
        except Exception as e:
            logger.error("Error resolving claim: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                _t("common.error", default="Error"),
                str(e),
            )
