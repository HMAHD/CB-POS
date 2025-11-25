from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableView, QHeaderView, QAbstractItemView, QMessageBox
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QTimer
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from cbpos.core.services.product_service import ProductService
from cbpos.ui.dialogs.product_editor_dialog import ProductEditorDialog

class ProductTableModel(QAbstractTableModel):
    def __init__(self, products=None):
        super().__init__()
        self.products = products or []
        self.headers = ["ID", "Barcode", "Name (EN)", "Price", "Stock", "Cost", "Weighted", "Category"]

    def rowCount(self, parent=QModelIndex()):
        return len(self.products)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        
        product = self.products[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0: return str(product.id)
            elif col == 1: return product.barcode
            elif col == 2: return product.name_en
            elif col == 3: return f"{product.price:.2f}"
            elif col == 4: return f"{product.stock_qty:.3f}"
            elif col == 5: return f"{product.cost:.2f}"
            elif col == 6: return "Yes" if product.is_weighted else "No"
            elif col == 7: return product.category.name if product.category else "-"
        
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def update_data(self, products):
        self.beginResetModel()
        self.products = products
        self.endResetModel()

class InventoryMasterView(QWidget):
    def __init__(self):
        super().__init__()
        self.product_service = ProductService()
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Inventory Master")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #00BCEB;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        self.btn_add = QPushButton("Add Product (F2)")
        self.btn_add.clicked.connect(self.open_add_dialog)
        self.btn_add.setShortcut("F2")
        header_layout.addWidget(self.btn_add)
        
        self.btn_refresh = QPushButton("Refresh (F5)")
        self.btn_refresh.clicked.connect(self.load_data)
        self.btn_refresh.setShortcut("F5")
        header_layout.addWidget(self.btn_refresh)
        
        layout.addLayout(header_layout)

        # Search
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Name or Barcode...")
        self.search_input.textChanged.connect(self.on_search_changed)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Table
        self.table = QTableView()
        self.model = ProductTableModel()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self.on_row_double_clicked)
        layout.addWidget(self.table)
        
        # Debounce timer for search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

    def load_data(self):
        # Initial load - get all or top 100
        # For now, let's just search empty string which returns all (or limit in service)
        self.perform_search()

    def on_search_changed(self):
        self.search_timer.start(300) # 300ms debounce

    def perform_search(self):
        query = self.search_input.text()
        products = self.product_service.search_products(query)
        self.model.update_data(products)

    def open_add_dialog(self):
        dialog = ProductEditorDialog(parent=self)
        if dialog.exec():
            self.load_data()

    def on_row_double_clicked(self, index):
        product = self.model.products[index.row()]
        self.open_edit_dialog(product)

    def open_edit_dialog(self, product):
        dialog = ProductEditorDialog(product, parent=self)
        if dialog.exec():
            self.load_data()
