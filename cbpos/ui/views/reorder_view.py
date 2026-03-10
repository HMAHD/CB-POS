from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from decimal import Decimal
from cbpos.core.services.stock_service import StockService
from cbpos.i18n import _t


class ReorderView(QWidget):
    """
    Reorder Report View - Shows products that need restocking.
    Displays items where stock_qty <= reorder_point.
    """

    navigate_to_purchase = pyqtSignal(list)  # Signal to navigate with pre-filled items

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_reorder_items()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel(_t("reorder.title"))
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Info text
        info = QLabel(_t("reorder.info_text"))
        info.setProperty("class", "muted")
        layout.addWidget(info)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
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
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()

        btn_refresh = QPushButton(_t("common.refresh"))
        btn_refresh.clicked.connect(self.load_reorder_items)
        btn_layout.addWidget(btn_refresh)

        btn_layout.addStretch()

        btn_create_po = QPushButton(_t("reorder.create_purchase_order"))
        btn_create_po.setProperty("class", "primary")
        btn_create_po.clicked.connect(self.create_purchase_order)
        btn_layout.addWidget(btn_create_po)

        layout.addLayout(btn_layout)

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
                name_item.setForeground(QColor("#FF4136"))
            self.table.setItem(row, 0, name_item)

            # Barcode
            self.table.setItem(row, 1, QTableWidgetItem(product.barcode))

            # Current Stock
            stock_item = QTableWidgetItem("{0:.3f}".format(product.stock_qty))
            stock_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if product.stock_qty <= 0:
                stock_item.setForeground(QColor("#FF4136"))
            self.table.setItem(row, 2, stock_item)

            # Reorder Point
            reorder_item = QTableWidgetItem("{0:.3f}".format(product.reorder_point))
            reorder_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, reorder_item)

            # Preferred Qty
            preferred_item = QTableWidgetItem("{0:.3f}".format(product.preferred_qty))
            preferred_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, preferred_item)

            # Supplier (first one if exists)
            supplier_name = product.suppliers[0].name if product.suppliers else _t("reorder.no_supplier")
            self.table.setItem(row, 5, QTableWidgetItem(supplier_name))

            # Store product ID in row data
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, product.id)

    def create_purchase_order(self):
        """
        Create purchase order from selected items.
        Navigate to PurchaseView with pre-filled quantities.
        """
        selected_rows = set(item.row() for item in self.table.selectedItems())

        if not selected_rows:
            QMessageBox.warning(
                self,
                _t("reorder.no_selection"),
                _t("reorder.no_selection_msg"),
            )
            return

        # Collect items with calculated order quantities from table data
        po_items = []
        for row in sorted(selected_rows):
            product_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            product_name = self.table.item(row, 0).text()
            current_stock = Decimal(self.table.item(row, 2).text())
            preferred_qty = Decimal(self.table.item(row, 4).text())
            supplier = self.table.item(row, 5).text()

            order_qty = max(preferred_qty - current_stock, Decimal("0"))

            po_items.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "current_stock": current_stock,
                    "order_qty": order_qty,
                    "supplier": supplier if supplier != _t("reorder.no_supplier") else "",
                }
            )

        # Emit signal to navigate to Purchase View with items
        self.navigate_to_purchase.emit(po_items)
        QMessageBox.information(
            self,
            _t("reorder.purchase_order"),
            _t("reorder.purchase_order_created", count=len(po_items)),
        )
