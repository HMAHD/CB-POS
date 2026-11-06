from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
)

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Product
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.utils.permission_helper import check_permission_with_override
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class StockAdjustmentDialog(QDialog):
    """Dialog to record a manual stock quantity change (damage, theft, expiry, correction, etc.)."""

    def __init__(self, product: Product, inventory_service: InventoryService | None = None, parent=None):
        """Build the dialog for adjusting stock of `product`."""
        super().__init__(parent)
        self.setObjectName("StockAdjustmentDialog")
        self.product = product
        self.inventory_service = inventory_service or InventoryService()

        self.setWindowTitle(_t("stock_adjust.title", name=product.name_en))
        self.setMinimumWidth(440)
        self.init_ui()
        install_wheel_guard(self)

    def _format_qty(self, qty: Decimal) -> str:
        """Format stock quantity with 3 decimal places if weighted, else integer."""
        if self.product.is_weighted:
            return f"{qty:.3f}"
        return f"{qty:.0f}"

    def init_ui(self):
        """Build form fields, preview label, and footer buttons."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # In stock header
        self.lbl_in_stock = QLabel(_t("stock_adjust.in_stock", qty=self._format_qty(self.product.stock_qty)))
        self.lbl_in_stock.setProperty("class", "metric-value")
        self.lbl_in_stock.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.lbl_in_stock)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(12)

        # Mode row: (•) Remove  ( ) Add   Quantity: [ 2 ]
        mode_qty_layout = QHBoxLayout()
        mode_qty_layout.setSpacing(12)

        self.mode_group = QButtonGroup(self)
        self.radio_remove = QRadioButton(_t("stock_adjust.remove"))
        self.radio_remove.setObjectName("RadioRemove")
        self.radio_remove.setChecked(True)
        self.radio_add = QRadioButton(_t("stock_adjust.add"))
        self.radio_add.setObjectName("RadioAdd")

        self.mode_group.addButton(self.radio_remove)
        self.mode_group.addButton(self.radio_add)
        mode_qty_layout.addWidget(self.radio_remove)
        mode_qty_layout.addWidget(self.radio_add)
        mode_qty_layout.addSpacing(16)

        lbl_qty = QLabel(_t("stock_adjust.quantity") + ":")
        mode_qty_layout.addWidget(lbl_qty)

        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setObjectName("QtySpin")
        if self.product.is_weighted:
            self.qty_spin.setDecimals(3)
            self.qty_spin.setSingleStep(0.100)
            self.qty_spin.setRange(0.001, 999999.0)
            self.qty_spin.setValue(1.0)
        else:
            self.qty_spin.setDecimals(0)
            self.qty_spin.setSingleStep(1.0)
            self.qty_spin.setRange(1.0, 999999.0)
            self.qty_spin.setValue(1.0)
        self.qty_spin.setFixedWidth(110)
        mode_qty_layout.addWidget(self.qty_spin)
        mode_qty_layout.addStretch()

        form_layout.addRow("", mode_qty_layout)

        # Reason combo
        self.cmb_reason = QComboBox()
        self.cmb_reason.setObjectName("CmbReason")
        self.cmb_reason.addItem(_t("stock_adjust.reason_damaged"), "DAMAGED")
        self.cmb_reason.addItem(_t("stock_adjust.reason_expired"), "EXPIRED")
        self.cmb_reason.addItem(_t("stock_adjust.reason_theft"), "THEFT")
        self.cmb_reason.addItem(_t("stock_adjust.reason_found"), "FOUND")
        self.cmb_reason.addItem(_t("stock_adjust.reason_correction"), "CORRECTION")
        self.cmb_reason.addItem(_t("stock_adjust.reason_other"), "OTHER")
        form_layout.addRow(_t("stock_adjust.reason") + ":", self.cmb_reason)

        # Note field
        self.txt_note = QLineEdit()
        self.txt_note.setObjectName("TxtNote")
        self.txt_note.setPlaceholderText(_t("stock_adjust.note"))
        form_layout.addRow(_t("stock_adjust.note") + ":", self.txt_note)

        # Live preview
        self.lbl_will_be = QLabel()
        self.lbl_will_be.setObjectName("LblWillBe")
        self.lbl_will_be.setStyleSheet("font-weight: 500;")
        form_layout.addRow("", self.lbl_will_be)

        # Warning label
        self.lbl_warning = QLabel()
        self.lbl_warning.setObjectName("LblWarning")
        self.lbl_warning.setStyleSheet("color: #FF4136; font-size: 12px;")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.hide()
        form_layout.addRow("", self.lbl_warning)

        layout.addLayout(form_layout)

        # Connect signals for live updates
        self.radio_remove.toggled.connect(self._update_preview)
        self.radio_add.toggled.connect(self._update_preview)
        self.qty_spin.valueChanged.connect(self._update_preview)
        self.cmb_reason.currentIndexChanged.connect(self._on_reason_changed)

        self._update_preview()

        # Dialog footer
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="stock_adjust.save",
            on_primary=self.save_adjustment,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnSave",
            cancel_object_name="BtnCancel",
        )
        layout.addLayout(footer_layout)

        # Initial focus
        self.qty_spin.setFocus()
        self.qty_spin.selectAll()

    def _on_reason_changed(self):
        """Update placeholder or validation indicator when reason changes."""
        reason_code = self.cmb_reason.currentData()
        if reason_code == "OTHER":
            self.txt_note.setPlaceholderText(_t("stock_adjust.note_required"))
        else:
            self.txt_note.setPlaceholderText(_t("stock_adjust.note"))

    def _update_preview(self):
        """Update the live preview of the resulting stock quantity."""
        qty = Decimal(str(self.qty_spin.value()))
        delta = -qty if self.radio_remove.isChecked() else qty
        new_qty = self.product.stock_qty + delta
        self.lbl_will_be.setText(_t("stock_adjust.will_be", qty=self._format_qty(new_qty)))

        allow_negative = bool(ConfigService.get("allow_negative_stock"))
        if new_qty < 0 and not allow_negative:
            self.lbl_warning.setText(_t("stock_adjust.negative_blocked"))
            self.lbl_warning.show()
        else:
            self.lbl_warning.setText("")
            self.lbl_warning.hide()

    def save_adjustment(self):
        """Validate input, verify permission with override, and perform the adjustment."""
        reason_code = self.cmb_reason.currentData()
        note = self.txt_note.text().strip()

        if reason_code == "OTHER" and not note:
            QMessageBox.warning(self, _t("common.validation_error"), _t("stock_adjust.note_required"))
            self.txt_note.setFocus()
            return

        qty = Decimal(str(self.qty_spin.value()))
        if qty <= 0:
            QMessageBox.warning(self, _t("common.validation_error"), _t("stock_adjustment.invalid_amount"))
            self.qty_spin.setFocus()
            return

        qty_change = -qty if self.radio_remove.isChecked() else qty
        new_qty = self.product.stock_qty + qty_change

        allow_negative = bool(ConfigService.get("allow_negative_stock"))
        if new_qty < 0 and not allow_negative:
            QMessageBox.warning(self, _t("common.validation_error"), _t("stock_adjust.negative_blocked"))
            return

        # Check permission with manager override
        user = check_permission_with_override(Permissions.INVENTORY_STOCK_ADJUST, self)
        if not user:
            return

        try:
            self.inventory_service.adjust_stock(
                product_id=self.product.id,
                qty_change=qty_change,
                reason=reason_code,
                user_id=user.id,
                note=note,
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))
