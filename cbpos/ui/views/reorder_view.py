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
from cbpos.core.database import Database
from cbpos.core.models import Product
from sqlalchemy import select


class ReorderView(QWidget):
    """
    Reorder Report View - Shows products that need restocking.
    Displays items where stock_qty <= reorder_point.
    """

    navigate_to_purchase = pyqtSignal(list)  # Signal to navigate with pre-filled items

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.init_ui()
        self.load_reorder_items()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Reorder Report - Low Stock Items")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(title)

        # Info text
        info = QLabel("Products that need restocking (Stock ≤ Reorder Point)")
        info.setStyleSheet("color: #AAAAAA; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(info)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                "Product",
                "Barcode",
                "Current Stock",
                "Reorder Point",
                "Preferred Qty",
                "Supplier",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(
            """
            QTableWidget {
                background-color: #001F3F;
                color: white;
                border: 1px solid #003366;
                gridline-color: #003366;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #00BCEB;
                color: black;
            }
            QHeaderView::section {
                background-color: #003366;
                color: white;
                padding: 8px;
                border: 1px solid #001F3F;
                font-weight: bold;
            }
        """
        )
        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(
            "background-color: #003366; color: white; padding: 10px; font-weight: bold;"
        )
        btn_refresh.clicked.connect(self.load_reorder_items)
        btn_layout.addWidget(btn_refresh)

        btn_layout.addStretch()

        btn_create_po = QPushButton("Create Purchase Order")
        btn_create_po.setStyleSheet(
            "background-color: #39FF14; color: black; padding: 10px; font-weight: bold;"
        )
        btn_create_po.clicked.connect(self.create_purchase_order)
        btn_layout.addWidget(btn_create_po)

        layout.addLayout(btn_layout)

    def load_reorder_items(self):
        """Load products where stock_qty <= reorder_point."""
        with self.db.get_session() as session:
            # Query products that need reordering
            products = session.scalars(
                select(Product)
                .where(Product.stock_qty <= Product.reorder_point)
                .where(Product.is_active == True)  # noqa: E712
                .order_by(Product.stock_qty)
            ).all()

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
                stock_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                if product.stock_qty <= 0:
                    stock_item.setForeground(QColor("#FF4136"))
                self.table.setItem(row, 2, stock_item)

                # Reorder Point
                reorder_item = QTableWidgetItem("{0:.3f}".format(product.reorder_point))
                reorder_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row, 3, reorder_item)

                # Preferred Qty
                preferred_item = QTableWidgetItem(
                    "{0:.3f}".format(product.preferred_qty)
                )
                preferred_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row, 4, preferred_item)

                # Supplier (first one if exists)
                supplier_name = (
                    product.suppliers[0].name if product.suppliers else "No Supplier"
                )
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
                "No Selection",
                "Please select items to add to purchase order.",
            )
            return

        # Collect items with calculated order quantities
        po_items = []
        with self.db.get_session() as session:
            for row in sorted(selected_rows):
                product_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                product = session.get(Product, product_id)

                if product:
                    # Calculate order qty = Preferred - Current
                    order_qty = max(product.preferred_qty - product.stock_qty, 0)

                    po_items.append(
                        {
                            "product_id": product.id,
                            "product_name": product.name_en,
                            "current_stock": product.stock_qty,
                            "order_qty": order_qty,
                            "supplier": (
                                product.suppliers[0].name if product.suppliers else ""
                            ),
                        }
                    )

        # Emit signal to navigate to Purchase View with items
        self.navigate_to_purchase.emit(po_items)
        QMessageBox.information(
            self,
            "Purchase Order",
            "Created purchase order with {0} items.\nNavigating to Purchase view...".format(
                len(po_items)
            ),
        )
