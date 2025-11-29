"""
Advanced Product Search Dialog ([F3]).
Supports filters: Category, Supplier, Price Range.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QComboBox,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QDoubleSpinBox,
    QHeaderView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence
from decimal import Decimal
from sqlalchemy import select
from cbpos.core.services.product_service import ProductService
from cbpos.core.models import Category, Supplier
from cbpos.core.database import Database


class AdvancedSearchDialog(QDialog):
    """
    Advanced Product Search Dialog (F3).
    Supports filters: Category, Supplier, Price Range.
    """

    product_selected = pyqtSignal(object)  # Emits selected Product

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Search [F3]")
        self.setMinimumSize(900, 600)
        self.product_service = ProductService()
        self.db = Database()
        self.init_ui()
        self.load_filters()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Advanced Product Search")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(title)

        # Filters
        filter_layout = QFormLayout()

        # Search Query
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter product name or barcode...")
        self.search_input.textChanged.connect(self.perform_search)
        filter_layout.addRow("Search:", self.search_input)

        # Category Filter
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        self.category_combo.currentIndexChanged.connect(self.perform_search)
        filter_layout.addRow("Category:", self.category_combo)

        # Supplier Filter
        self.supplier_combo = QComboBox()
        self.supplier_combo.addItem("All Suppliers", None)
        self.supplier_combo.currentIndexChanged.connect(self.perform_search)
        filter_layout.addRow("Supplier:", self.supplier_combo)

        # Price Range
        price_layout = QHBoxLayout()
        self.price_min = QDoubleSpinBox()
        self.price_min.setRange(0, 999999)
        self.price_min.setPrefix("Rs. ")
        self.price_min.valueChanged.connect(self.perform_search)

        self.price_max = QDoubleSpinBox()
        self.price_max.setRange(0, 999999)
        self.price_max.setValue(999999)
        self.price_max.setPrefix("Rs. ")
        self.price_max.valueChanged.connect(self.perform_search)

        price_layout.addWidget(self.price_min)
        price_layout.addWidget(QLabel(" to "))
        price_layout.addWidget(self.price_max)
        filter_layout.addRow("Price Range:", price_layout)

        layout.addLayout(filter_layout)

        # Results Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Barcode", "Stock", "Price", "Category"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.on_select)
        self.table.setStyleSheet(
            """
            QTableWidget {
                background-color: #001F3F;
                color: white;
                border: 1px solid #003366;
            }
            QHeaderView::section {
                background-color: #003366;
                color: white;
                padding: 8px;
                font-weight: bold;
            }
        """
        )
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_select = QPushButton("Select [Enter]")
        btn_select.setStyleSheet(
            "background-color: #39FF14; color: black; padding: 10px; font-weight: bold;"
        )
        btn_select.clicked.connect(self.on_select)
        btn_layout.addWidget(btn_select)

        btn_cancel = QPushButton("Cancel [Esc]")
        btn_cancel.setStyleSheet(
            "background-color: #003366; color: white; padding: 10px; font-weight: bold;"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(
            self.on_select
        )
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.reject)

        # Focus
        self.search_input.setFocus()

    def load_filters(self):
        """Load categories and suppliers for filters."""
        # Load Categories
        with self.db.get_session() as session:
            categories = session.scalars(select(Category)).all()
            for cat in categories:
                self.category_combo.addItem(cat.name, cat.id)

            suppliers = session.scalars(select(Supplier)).all()
            for sup in suppliers:
                self.supplier_combo.addItem(sup.company_name, sup.id)

    def perform_search(self):
        """Execute search with filters."""
        query = self.search_input.text()
        category_id = self.category_combo.currentData()
        supplier_id = self.supplier_combo.currentData()
        min_price = Decimal(str(self.price_min.value()))
        max_price = Decimal(str(self.price_max.value()))

        # Get products
        products = self.product_service.search_products(query, mode="ALL")

        # Apply filters
        filtered = []
        for p in products:
            # Category filter
            if category_id and p.category_id != category_id:
                continue
            # Supplier filter
            if supplier_id and p.default_supplier_id != supplier_id:
                continue
            # Price filter
            if not (min_price <= p.price <= max_price):
                continue
            filtered.append(p)

        # Populate table
        self.table.setRowCount(len(filtered))
        for row, product in enumerate(filtered):
            self.table.setItem(row, 0, QTableWidgetItem(product.name_en))
            self.table.setItem(row, 1, QTableWidgetItem(product.barcode))

            stock_item = QTableWidgetItem(f"{float(product.stock_qty): .2f}")
            stock_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 2, stock_item)

            price_item = QTableWidgetItem(f"Rs. {float(product.price): .2f}")
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 3, price_item)

            cat_name = product.category.name if product.category else "-"
            self.table.setItem(row, 4, QTableWidgetItem(cat_name))

            # Store product object
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, product)

    def on_select(self):
        """Emit selected product and close dialog."""
        row = self.table.currentRow()
        if row >= 0:
            product = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.product_selected.emit(product)
            self.accept()
