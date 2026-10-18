from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.models import Product
from cbpos.core.services.inventory_service import InventoryService
from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class StockAdjustmentDialog(QDialog):
    """Dialog to record a manual stock quantity change (count, damage, return, etc.) for a product."""

    def __init__(self, product: Product, parent=None):
        """Build the dialog for adjusting stock of `product`."""
        super().__init__(parent)
        self.product = product

        self.setWindowTitle(_t("stock_adjustment.title", product_name=product.name_en))
        self.setFixedSize(400, 300)
        self.init_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def init_ui(self):
        """Build the current-stock display, adjustment amount field, reason combo, and buttons."""
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setSpacing(12)

        self.lbl_current = QLabel(f"{self.product.stock_qty:.3f}")
        self.lbl_current.setProperty("class", "credit")

        self.txt_change = QLineEdit()
        self.txt_change.setPlaceholderText(_t("stock_adjustment.adjustment_placeholder"))
        # Allow negative numbers
        self.txt_change.setValidator(QDoubleValidator(-99999.99, 99999.99, 3))

        self.cmb_reason = QComboBox()
        self.cmb_reason.addItem(_t("stock_adjustment.reason_inventory_count"), "Inventory Count")
        self.cmb_reason.addItem(_t("stock_adjustment.reason_damage"), "Damage/Spoilage")
        self.cmb_reason.addItem(_t("stock_adjustment.reason_return"), "Return")
        self.cmb_reason.addItem(_t("stock_adjustment.reason_other"), "Other")

        form_layout.addRow(_t("stock_adjustment.current_stock"), self.lbl_current)
        form_layout.addRow(_t("stock_adjustment.adjustment"), self.txt_change)
        form_layout.addRow(_t("stock_adjustment.reason"), self.cmb_reason)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()

        self.btn_cancel = QPushButton(_t("stock_adjustment.btn_cancel"))
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton(_t("stock_adjustment.btn_save"))
        self.btn_save.setProperty("class", "accent")
        self.btn_save.clicked.connect(self.save_adjustment)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def save_adjustment(self):
        """Check permission, validate the entered change, and apply it via `InventoryService.adjust_stock`."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.INVENTORY_STOCK_ADJUST, self):
            return

        try:
            change = Decimal(self.txt_change.text())
        except Exception:
            QMessageBox.warning(self, _t("common.error"), _t("stock_adjustment.invalid_amount"))
            return

        reason = self.cmb_reason.currentData()

        if change == 0:
            return

        if InventoryService.adjust_stock(self.product.id, change, reason):
            QMessageBox.information(self, _t("common.success"), _t("stock_adjustment.success_message"))
            self.accept()
        else:
            QMessageBox.critical(
                self, _t("common.error"), _t("stock_adjustment.failed_message", error=_t("common.unknown_error"))
            )
