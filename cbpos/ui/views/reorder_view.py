"""Reorder view listing products that have fallen at or below their reorder point."""

from decimal import Decimal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.purchase_order_service import PurchaseOrderService
from cbpos.core.services.stock_service import StockService
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, status_color
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    configure_table_columns,
)


class ReorderView(QWidget):
    """
    Reorder Report View - Shows products that need restocking.
    Displays items where stock_qty <= reorder_point.
    """

    # Signal to navigate to Purchase View with pre-filled items and the id
    # of the Purchase Order just persisted for them (#486).
    navigate_to_purchase = pyqtSignal(list, int)

    def __init__(self):
        """Build the UI and load the initial reorder list."""
        super().__init__()
        self.user = None
        self.init_ui()
        self.load_reorder_items()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self):
        """Build the title, info text, reorder table, and action buttons."""
        layout = QVBoxLayout(self)

        # Title
        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        layout.addWidget(self.lbl_title)

        # Info text
        self.lbl_info = QLabel()
        self.lbl_info.setProperty("class", "muted")
        layout.addWidget(self.lbl_info)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
                5: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.empty_state_widget = attach_table_empty_state(self.table, Icons.REORDER, "common.no_items")
        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.load_reorder_items)
        btn_layout.addWidget(self.btn_refresh)

        btn_layout.addStretch()

        self.btn_create_po = QPushButton()
        self.btn_create_po.setProperty("class", "primary")
        self.btn_create_po.clicked.connect(self.create_purchase_order)
        btn_layout.addWidget(self.btn_create_po)

        layout.addLayout(btn_layout)

    def retranslate_ui(self):
        """Update all translatable strings."""
        self.lbl_title.setText(_t("reorder.title"))
        self.lbl_info.setText(_t("reorder.info_text"))
        self.btn_refresh.setText(_t("common.refresh"))
        self.btn_create_po.setText(_t("reorder.create_purchase_order"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("reorder.product"),
                _t("reorder.barcode"),
                _t("reorder.current_stock"),
                _t("reorder.reorder_point"),
                _t("reorder.preferred_qty"),
                _t("reorder.supplier"),
            ]
        )
        align_numeric_headers(self.table, [2, 3, 4])

    def set_user(self, user):
        """Store the logged-in user for use when persisting a Purchase Order."""
        self.user = user

    def load_reorder_items(self):
        """Load products where stock_qty <= reorder_point."""
        products = StockService.get_reorder_list()

        self.table.setRowCount(len(products))

        for row, product in enumerate(products):
            # Product Name
            name_item = QTableWidgetItem(product.name_en)
            if product.stock_qty <= 0:
                # Out of stock - Bold Red
                font = QFont()
                font.setBold(True)
                name_item.setFont(font)
                name_item.setForeground(status_color(DANGER))
            self.table.setItem(row, 0, name_item)

            # Barcode
            self.table.setItem(row, 1, QTableWidgetItem(product.barcode))

            # Current Stock
            stock_item = QTableWidgetItem(f"{product.stock_qty:.3f}")
            stock_item.setTextAlignment(NUMERIC_ALIGNMENT)
            if product.stock_qty <= 0:
                stock_item.setForeground(status_color(DANGER))
            self.table.setItem(row, 2, stock_item)

            # Reorder Point
            reorder_item = QTableWidgetItem(f"{product.reorder_point:.3f}")
            reorder_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 3, reorder_item)

            # Preferred Qty
            preferred_item = QTableWidgetItem(f"{product.preferred_qty:.3f}")
            preferred_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 4, preferred_item)

            # Supplier (first one if exists) — store its id in UserRole+1
            # (None sentinel if the product has no supplier assigned) so
            # create_purchase_order() can persist a real Purchase Order
            # against it (#486).
            has_supplier = bool(product.suppliers)
            supplier_name = product.suppliers[0].company_name if has_supplier else _t("reorder.no_supplier")
            supplier_item = QTableWidgetItem(supplier_name)
            supplier_item.setData(Qt.ItemDataRole.UserRole + 1, product.suppliers[0].id if has_supplier else None)
            self.table.setItem(row, 5, supplier_item)

            # Store product ID in row data
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, product.id)

    def create_purchase_order(self):
        """
        Create a real Purchase Order (#486) from selected items, then
        navigate to PurchaseView with the GRN pre-filled from it.

        All selected rows must share the same (non-empty) supplier, since a
        Purchase Order is placed with one supplier -- this mirrors the
        existing one-supplier-per-GRN constraint on the New GRN tab.
        """
        selected_rows = {item.row() for item in self.table.selectedItems()}

        if not selected_rows:
            QMessageBox.warning(
                self,
                _t("reorder.no_selection"),
                _t("reorder.no_selection_msg"),
            )
            return

        # Collect items with calculated order quantities from table data
        po_items = []
        supplier_ids = set()
        for row in sorted(selected_rows):
            product_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            product_name = self.table.item(row, 0).text()
            barcode = self.table.item(row, 1).text()
            current_stock = Decimal(self.table.item(row, 2).text())
            preferred_qty = Decimal(self.table.item(row, 4).text())
            supplier_id = self.table.item(row, 5).data(Qt.ItemDataRole.UserRole + 1)
            supplier_ids.add(supplier_id)

            order_qty = max(preferred_qty - current_stock, Decimal("0"))

            po_items.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "barcode": barcode,
                    "current_stock": current_stock,
                    "order_qty": order_qty,
                }
            )

        if supplier_ids != {next(iter(supplier_ids))} or None in supplier_ids:
            QMessageBox.warning(
                self,
                _t("reorder.mixed_supplier_title"),
                _t("reorder.mixed_supplier_msg"),
            )
            return

        supplier_id = next(iter(supplier_ids))
        order = PurchaseOrderService.create_purchase_order(
            supplier_id=supplier_id,
            user_id=self.user.id,
            items=[
                {
                    "product_id": item["product_id"],
                    "qty_ordered": item["order_qty"] if item["order_qty"] > 0 else Decimal("1.000"),
                }
                for item in po_items
            ],
        )

        # Emit signal to navigate to Purchase View with items and the order id
        self.navigate_to_purchase.emit(po_items, order.id)
        QMessageBox.information(
            self,
            _t("reorder.purchase_order"),
            _t("reorder.purchase_order_created", count=len(po_items), doc_number=order.document_number),
        )
