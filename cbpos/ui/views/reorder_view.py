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
from cbpos.ui.components.activation import Activatable
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, status_color
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)


class ReorderView(QWidget, Activatable):
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
        rows = StockService.get_reorder_rows()

        with batch_table_update(self.table):
            self.table.setRowCount(len(rows))

            # Hoist LEGB locals
            table = self.table
            set_item = table.setItem
            TableItem = QTableWidgetItem
            num_align = NUMERIC_ALIGNMENT
            user_role = Qt.ItemDataRole.UserRole
            user_role_plus_1 = Qt.ItemDataRole.UserRole + 1
            color_danger = status_color(DANGER)
            no_supplier_str = _t("reorder.no_supplier")

            bold_font = QFont()
            bold_font.setBold(True)

            for row, row_data in enumerate(rows):
                # Product Name
                name_item = TableItem(row_data.name_en)
                if row_data.stock_qty <= 0:
                    # Out of stock - Bold Red
                    name_item.setFont(bold_font)
                    name_item.setForeground(color_danger)
                name_item.setData(user_role, row_data.product_id)
                set_item(row, 0, name_item)

                # Barcode
                set_item(row, 1, TableItem(row_data.barcode))

                # Current Stock
                stock_item = TableItem(f"{row_data.stock_qty:.3f}")
                stock_item.setTextAlignment(num_align)
                if row_data.stock_qty <= 0:
                    stock_item.setForeground(color_danger)
                set_item(row, 2, stock_item)

                # Reorder Point
                reorder_item = TableItem(f"{row_data.reorder_point:.3f}")
                reorder_item.setTextAlignment(num_align)
                set_item(row, 3, reorder_item)

                # Preferred Qty
                preferred_item = TableItem(f"{row_data.preferred_qty:.3f}")
                preferred_item.setTextAlignment(num_align)
                set_item(row, 4, preferred_item)

                # Supplier (resolved by StockService)
                has_supplier = row_data.supplier_id is not None
                supplier_name = row_data.supplier_name if has_supplier else no_supplier_str
                supplier_item = TableItem(supplier_name)
                supplier_item.setData(user_role_plus_1, row_data.supplier_id)
                set_item(row, 5, supplier_item)

    def create_purchase_order(self):
        """
        Create a real Purchase Order (#486, #864) from selected items, then
        navigate to PurchaseView with the GRN pre-filled from it.

        Supports multi-supplier selection by offering to split into one PO per
        supplier. Rows with no supplier are excluded with an actionable hint.
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
        by_supplier: dict[int, list[dict]] = {}
        no_supplier_items: list[dict] = []

        for row in sorted(selected_rows):
            product_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            product_name = self.table.item(row, 0).text()
            barcode = self.table.item(row, 1).text()
            current_stock = Decimal(self.table.item(row, 2).text())
            preferred_qty = Decimal(self.table.item(row, 4).text())
            supplier_id = self.table.item(row, 5).data(Qt.ItemDataRole.UserRole + 1)

            order_qty = max(preferred_qty - current_stock, Decimal("0"))
            po_item = {
                "product_id": product_id,
                "product_name": product_name,
                "barcode": barcode,
                "current_stock": current_stock,
                "order_qty": order_qty,
            }

            if supplier_id is None:
                no_supplier_items.append(po_item)
            else:
                by_supplier.setdefault(supplier_id, []).append(po_item)

        if not by_supplier:
            hint = _t("reorder.no_supplier_hint")
            if no_supplier_items:
                names = "\n• " + "\n• ".join(i["product_name"] for i in no_supplier_items)
                msg = f"{hint}\n{names}"
            else:
                msg = hint
            QMessageBox.warning(
                self,
                _t("reorder.purchase_order"),
                msg,
            )
            return

        if len(by_supplier) > 1:
            confirm_msg = _t("reorder.split_confirm", count=len(by_supplier))
            if no_supplier_items:
                names = "\n• " + "\n• ".join(i["product_name"] for i in no_supplier_items)
                confirm_msg = f"{confirm_msg}\n\n{_t('reorder.no_supplier_hint')}\n{names}"
            reply = QMessageBox.question(
                self,
                _t("reorder.purchase_order"),
                confirm_msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        elif no_supplier_items:
            names = "\n• " + "\n• ".join(i["product_name"] for i in no_supplier_items)
            QMessageBox.information(
                self,
                _t("reorder.purchase_order"),
                f"{_t('reorder.no_supplier_hint')}\n{names}",
            )

        created_orders = []
        for s_id, items in by_supplier.items():
            order = PurchaseOrderService.create_purchase_order(
                supplier_id=s_id,
                user_id=self.user.id,
                items=[
                    {
                        "product_id": item["product_id"],
                        "qty_ordered": item["order_qty"] if item["order_qty"] > 0 else Decimal("1.000"),
                    }
                    for item in items
                ],
            )
            created_orders.append((items, order))

        if not created_orders:
            return

        # Emit signal to navigate to Purchase View with items and the first order id
        first_items, first_order = created_orders[0]
        self.navigate_to_purchase.emit(first_items, first_order.id)

        if len(created_orders) == 1:
            QMessageBox.information(
                self,
                _t("reorder.purchase_order"),
                _t("reorder.purchase_order_created", count=len(first_items), doc_number=first_order.document_number),
            )
        else:
            doc_numbers = ", ".join(o.document_number for _, o in created_orders)
            QMessageBox.information(
                self,
                _t("reorder.purchase_order"),
                _t("reorder.purchase_orders_created", count=len(created_orders), doc_numbers=doc_numbers),
            )

    def on_activated(self) -> None:
        """Reload when this view is shown again, so the user never sees stale data."""
        self.load_reorder_items()
