from decimal import Decimal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QDialogButtonBox,
    QCheckBox,
    QMessageBox,
    QTabWidget,
    QWidget,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHBoxLayout,
    QHeaderView,
    QSpinBox,
)

from sqlalchemy import select
from cbpos.core.models import Product, Category, CompositeItem
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.database import Database


class ProductEditor(QDialog):
    def __init__(self, product: Product = None, parent=None):
        super().__init__(parent)
        self.product = product
        self.inventory_service = InventoryService()
        self.setWindowTitle("Product Editor" if product else "New Product")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self.categories = []
        self.load_categories()

        self.setup_ui()
        if product:
            self.load_data()

    def load_categories(self):
        db = Database()
        with db.get_session() as session:
            self.categories = list(session.scalars(select(Category)).all())

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # Tab 1: General
        self.tab_general = QWidget()
        self.setup_general_tab()
        self.tabs.addTab(self.tab_general, "General")

        # Tab 2: Inventory
        self.tab_inventory = QWidget()
        self.setup_inventory_tab()
        self.tabs.addTab(self.tab_inventory, "Inventory")

        # Tab 3: Composition
        self.tab_composition = QWidget()
        self.setup_composition_tab()
        self.tabs.addTab(self.tab_composition, "Composition")

        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_product)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def setup_general_tab(self):
        layout = QFormLayout(self.tab_general)

        self.barcode_input = QLineEdit()
        self.name_en_input = QLineEdit()
        self.name_si_input = QLineEdit()
        self.name_ta_input = QLineEdit()

        self.category_combo = QComboBox()
        for cat in self.categories:
            self.category_combo.addItem(cat.name, cat.id)

        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 1000000)
        self.price_input.setDecimals(2)

        self.cost_input = QDoubleSpinBox()
        self.cost_input.setRange(0, 1000000)
        self.cost_input.setDecimals(2)

        layout.addRow("Barcode:", self.barcode_input)
        layout.addRow("Name (EN):", self.name_en_input)
        layout.addRow("Name (SI):", self.name_si_input)
        layout.addRow("Name (TA):", self.name_ta_input)
        layout.addRow("Category:", self.category_combo)
        layout.addRow("Price:", self.price_input)
        layout.addRow("Cost:", self.cost_input)

    def setup_inventory_tab(self):
        layout = QFormLayout(self.tab_inventory)

        self.stock_input = QDoubleSpinBox()
        self.stock_input.setRange(-10000, 1000000)
        self.stock_input.setDecimals(3)

        self.reorder_input = QSpinBox()
        self.reorder_input.setRange(0, 10000)

        self.preferred_qty_input = QSpinBox()
        self.preferred_qty_input.setRange(0, 10000)

        self.weighted_check = QCheckBox("Is Weighted Item?")

        layout.addRow("Stock Qty:", self.stock_input)
        layout.addRow("Reorder Level:", self.reorder_input)
        layout.addRow("Preferred Qty:", self.preferred_qty_input)
        layout.addRow("", self.weighted_check)

    def setup_composition_tab(self):
        layout = QVBoxLayout(self.tab_composition)

        # Add component area
        add_layout = QHBoxLayout()
        self.comp_barcode_input = QLineEdit()
        self.comp_barcode_input.setPlaceholderText("Scan/Enter Child Barcode")
        self.comp_qty_input = QDoubleSpinBox()
        self.comp_qty_input.setRange(0.001, 1000)
        self.comp_qty_input.setValue(1)
        add_btn = QPushButton("Add Component")
        add_btn.clicked.connect(self.add_component)

        add_layout.addWidget(self.comp_barcode_input)
        add_layout.addWidget(self.comp_qty_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        # Table
        self.comp_table = QTableWidget()
        self.comp_table.setColumnCount(4)
        self.comp_table.setHorizontalHeaderLabels(["ID", "Name", "Qty", "Action"])
        self.comp_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.comp_table.hideColumn(0)  # Hide ID
        layout.addWidget(self.comp_table)

    def add_component(self):
        barcode = self.comp_barcode_input.text().strip()
        qty = self.comp_qty_input.value()

        if not barcode:
            return

        product = self.inventory_service.get_product_by_barcode(barcode)
        if not product:
            QMessageBox.warning(self, "Error", "Product not found")
            return

        if self.product and product.id == self.product.id:
            QMessageBox.warning(self, "Error", "Cannot add self as component")
            return

        # Check if already exists in table
        for row in range(self.comp_table.rowCount()):
            if self.comp_table.item(row, 0).text() == str(product.id):
                QMessageBox.warning(self, "Error", "Component already added")
                return

        row = self.comp_table.rowCount()
        self.comp_table.insertRow(row)
        self.comp_table.setItem(row, 0, QTableWidgetItem(str(product.id)))
        self.comp_table.setItem(row, 1, QTableWidgetItem(product.name_en))
        self.comp_table.setItem(row, 2, QTableWidgetItem(str(qty)))

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(
            self.create_remove_handler(self.comp_table, remove_btn)
        )

        self.comp_table.setCellWidget(row, 3, remove_btn)
        self.comp_barcode_input.clear()

    def create_remove_handler(self, table, button):
        def handler():
            index = table.indexAt(button.pos())
            if index.isValid():
                table.removeRow(index.row())

        return handler

    def load_data(self):
        self.barcode_input.setText(self.product.barcode)
        self.barcode_input.setReadOnly(True)
        self.name_en_input.setText(self.product.name_en)
        self.name_si_input.setText(self.product.name_si or "")
        self.name_ta_input.setText(self.product.name_ta or "")

        index = self.category_combo.findData(self.product.category_id)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)

        self.price_input.setValue(float(self.product.price))
        self.cost_input.setValue(float(self.product.cost))

        self.stock_input.setValue(float(self.product.stock_qty))
        self.reorder_input.setValue(self.product.reorder_level)
        self.preferred_qty_input.setValue(self.product.preferred_qty)
        self.weighted_check.setChecked(self.product.is_weighted)

        # Load components
        db = Database()
        with db.get_session() as session:
            stmt = select(CompositeItem).where(
                CompositeItem.parent_product_id == self.product.id
            )
            components = session.scalars(stmt).all()

            for comp in components:
                row = self.comp_table.rowCount()
                self.comp_table.insertRow(row)
                self.comp_table.setItem(
                    row, 0, QTableWidgetItem(str(comp.child_product_id))
                )

                child = session.get(Product, comp.child_product_id)
                child_name = child.name_en if child else "Unknown"

                self.comp_table.setItem(row, 1, QTableWidgetItem(child_name))
                self.comp_table.setItem(row, 2, QTableWidgetItem(str(comp.qty)))

                remove_btn = QPushButton("Remove")
                remove_btn.clicked.connect(
                    self.create_remove_handler(self.comp_table, remove_btn)
                )
                self.comp_table.setCellWidget(row, 3, remove_btn)

    def save_product(self):
        data = {
            "barcode": self.barcode_input.text().strip(),
            "name_en": self.name_en_input.text().strip(),
            "name_si": self.name_si_input.text().strip(),
            "name_ta": self.name_ta_input.text().strip(),
            "category_id": self.category_combo.currentData(),
            "price": Decimal(str(self.price_input.value())),
            "cost": Decimal(str(self.cost_input.value())),
            "stock_qty": Decimal(str(self.stock_input.value())),
            "reorder_level": self.reorder_input.value(),
            "preferred_qty": self.preferred_qty_input.value(),
            "is_weighted": self.weighted_check.isChecked(),
            "is_active": True,
        }

        if not data["barcode"] or not data["name_en"]:
            QMessageBox.warning(self, "Error", "Barcode and Name are required")
            return

        if data["price"] <= 0:
            QMessageBox.warning(self, "Error", "Price must be > 0")
            return

        components = []
        for row in range(self.comp_table.rowCount()):
            child_id = int(self.comp_table.item(row, 0).text())
            qty = Decimal(self.comp_table.item(row, 2).text())
            components.append({"child_product_id": child_id, "qty": qty})

        data["components"] = components

        try:
            if self.product:
                self.inventory_service.update_product(self.product.id, data)
            else:
                if self.inventory_service.get_product_by_barcode(data["barcode"]):
                    QMessageBox.warning(self, "Error", "Barcode already exists")
                    return
                self.inventory_service.create_product(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
