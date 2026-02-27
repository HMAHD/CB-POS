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
    QLabel,
    QGroupBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QColor

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from cbpos.core.models import Product, Category, CompositeItem
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.database import Database


def _color_icon(hex_color: str, size: int = 12) -> QIcon:
    """Create a small colored square icon for category display."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(hex_color or "#FFFFFF"))
    return QIcon(pixmap)


class ProductEditor(QDialog):
    def __init__(self, product: Product = None, parent=None):
        super().__init__(parent)
        self.product = product
        self.inventory_service = InventoryService()
        self.setWindowTitle("Edit Product" if product else "Add New Product")
        self.setMinimumWidth(700)
        self.setMinimumHeight(520)
        self.resize(750, 580)

        self.categories = []
        self.suppliers = []
        self.load_categories()
        self.load_suppliers()

        self.setup_ui()
        if product:
            self.load_data()

    def load_categories(self):
        db = Database()
        with db.get_session() as session:
            self.categories = list(
                session.execute(
                    select(Category)
                    .options(joinedload(Category.subcategories))
                    .where(Category.parent_id.is_(None))
                    .order_by(Category.name)
                )
                .unique()
                .scalars()
                .all()
            )

    def load_suppliers(self):
        from cbpos.core.models import Supplier

        db = Database()
        with db.get_session() as session:
            self.suppliers = list(session.scalars(select(Supplier)).all())

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

        # Tab 4: Image
        self.tab_image = QWidget()
        self.setup_image_tab()
        self.tabs.addTab(self.tab_image, "Image")

        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_product)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def setup_general_tab(self):
        layout = QFormLayout(self.tab_general)
        layout.setVerticalSpacing(12)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name_en_input = QLineEdit()
        self.name_en_input.setPlaceholderText("Product name in English (required)")
        self.name_si_input = QLineEdit()
        self.name_si_input.setPlaceholderText("Optional")
        self.name_ta_input = QLineEdit()
        self.name_ta_input.setPlaceholderText("Optional")

        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan or type barcode (required)")

        self.category_combo = QComboBox()
        self.category_combo.addItem("-- Select Category --", None)
        for cat in self.categories:
            self.category_combo.addItem(_color_icon(cat.color), cat.name, cat.id)
            for sub in sorted(cat.subcategories, key=lambda c: c.name):
                self.category_combo.addItem(_color_icon(sub.color), f"    {sub.name}", sub.id)

        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 1000000)
        self.price_input.setDecimals(2)
        self.price_input.setPrefix("Rs. ")

        self.cost_input = QDoubleSpinBox()
        self.cost_input.setRange(0, 1000000)
        self.cost_input.setDecimals(2)
        self.cost_input.setPrefix("Rs. ")

        layout.addRow("Name (EN)*:", self.name_en_input)
        layout.addRow("Name (SI):", self.name_si_input)
        layout.addRow("Name (TA):", self.name_ta_input)
        layout.addRow("Barcode*:", self.barcode_input)
        layout.addRow("Category:", self.category_combo)
        layout.addRow("Selling Price*:", self.price_input)
        layout.addRow("Cost Price:", self.cost_input)

    def setup_inventory_tab(self):
        layout = QVBoxLayout(self.tab_inventory)
        layout.setSpacing(15)

        # Stock group
        grp_stock = QGroupBox("Stock")
        form_stock = QFormLayout(grp_stock)
        form_stock.setVerticalSpacing(12)
        form_stock.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.stock_input = QDoubleSpinBox()
        self.stock_input.setRange(-10000, 1000000)
        self.stock_input.setDecimals(3)

        self.reorder_input = QDoubleSpinBox()
        self.reorder_input.setRange(0, 10000)
        self.reorder_input.setDecimals(3)

        self.preferred_qty_input = QDoubleSpinBox()
        self.preferred_qty_input.setRange(0, 10000)
        self.preferred_qty_input.setDecimals(3)

        form_stock.addRow("Stock Qty:", self.stock_input)
        form_stock.addRow("Reorder Point:", self.reorder_input)
        form_stock.addRow("Preferred Qty:", self.preferred_qty_input)

        layout.addWidget(grp_stock)

        # Supplier group
        grp_supplier = QGroupBox("Supplier")
        form_supplier = QFormLayout(grp_supplier)
        form_supplier.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.supplier_combo = QComboBox()
        self.supplier_combo.addItem("-- No Default Supplier --", None)
        for supplier in self.suppliers:
            self.supplier_combo.addItem(supplier.company_name, supplier.id)
        form_supplier.addRow("Default Supplier:", self.supplier_combo)

        layout.addWidget(grp_supplier)

        # Unit of Measurement
        grp_unit = QGroupBox("Unit of Measurement")
        unit_layout = QHBoxLayout(grp_unit)

        self.unit_combo = QComboBox()
        self.unit_combo.addItem("-- None --", None)
        from cbpos.core.services.unit_service import UnitService

        for unit in UnitService.get_all():
            self.unit_combo.addItem(f"{unit.name} ({unit.abbreviation})", unit.id)
        unit_layout.addWidget(self.unit_combo)

        layout.addWidget(grp_unit)

        # Item type group
        grp_type = QGroupBox("Item Type")
        type_layout = QVBoxLayout(grp_type)
        type_layout.setSpacing(10)

        self.weighted_check = QCheckBox("Weighted Item (sold by kg)")
        self.service_check = QCheckBox("Service Item (no stock tracking)")

        type_layout.addWidget(self.weighted_check)
        type_layout.addWidget(self.service_check)

        layout.addWidget(grp_type)
        layout.addStretch()

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
        self.comp_barcode_input.returnPressed.connect(self.add_component)

        add_layout.addWidget(self.comp_barcode_input)
        add_layout.addWidget(self.comp_qty_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        # Table
        self.comp_table = QTableWidget()
        self.comp_table.setColumnCount(4)
        self.comp_table.setHorizontalHeaderLabels(["ID", "Name", "Qty", "Action"])
        self.comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.comp_table.hideColumn(0)  # Hide ID
        layout.addWidget(self.comp_table)

    def add_component(self):
        barcode = self.comp_barcode_input.text().strip()
        qty = self.comp_qty_input.value()

        if not barcode:
            return

        product = self.inventory_service.get_product_by_barcode(barcode)
        if not product:
            QMessageBox.warning(self, "Not Found", f"No product found with barcode '{barcode}'")
            self.comp_barcode_input.setFocus()
            return

        if self.product and product.id == self.product.id:
            QMessageBox.warning(self, "Invalid", "Cannot add self as component")
            return

        # Check if already exists in table
        for row in range(self.comp_table.rowCount()):
            if self.comp_table.item(row, 0).text() == str(product.id):
                QMessageBox.warning(self, "Duplicate", f"'{product.name_en}' is already added")
                return

        row = self.comp_table.rowCount()
        self.comp_table.insertRow(row)
        self.comp_table.setItem(row, 0, QTableWidgetItem(str(product.id)))
        self.comp_table.setItem(row, 1, QTableWidgetItem(product.name_en))
        self.comp_table.setItem(row, 2, QTableWidgetItem(str(qty)))

        remove_btn = QPushButton("Remove")
        target_row = row
        remove_btn.clicked.connect(lambda checked, r=target_row: self._remove_component(r))
        self.comp_table.setCellWidget(row, 3, remove_btn)

        self.comp_barcode_input.clear()
        self.comp_barcode_input.setFocus()

    def _remove_component(self, row: int) -> None:
        """Remove a component row. Re-wire buttons after removal."""
        if row < self.comp_table.rowCount():
            self.comp_table.removeRow(row)
            # Re-wire remove buttons with correct row indices
            for r in range(self.comp_table.rowCount()):
                btn = self.comp_table.cellWidget(r, 3)
                if btn:
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda checked, idx=r: self._remove_component(idx))

    def setup_image_tab(self):
        layout = QVBoxLayout(self.tab_image)

        self.lbl_image = QLabel("No Image Selected")
        self.lbl_image.setFixedSize(200, 200)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setStyleSheet(
            "border: 1px solid #3E3E42; background-color: #252526; color: #AAAAAA; border-radius: 4px;"
        )
        self.lbl_image.setScaledContents(True)

        btn_upload = QPushButton("Upload Image")
        btn_upload.clicked.connect(self.upload_image)

        btn_clear = QPushButton("Clear Image")
        btn_clear.clicked.connect(self.clear_image)

        layout.addWidget(self.lbl_image)
        layout.addWidget(btn_upload)
        layout.addWidget(btn_clear)
        layout.addStretch()

        self.current_image_path = None

    def upload_image(self):
        from PyQt6.QtWidgets import QFileDialog
        import shutil
        import os

        file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg)")

        if file_path:
            # Copy to assets
            filename = os.path.basename(file_path)
            target_dir = os.path.join(os.getcwd(), "cbpos", "assets", "product_images")
            os.makedirs(target_dir, exist_ok=True)

            target_path = os.path.join(target_dir, filename)
            shutil.copy(file_path, target_path)

            self.current_image_path = f"product_images/{filename}"
            self.show_image(target_path)

    def clear_image(self):
        self.current_image_path = None
        self.lbl_image.clear()
        self.lbl_image.setText("No Image Selected")

    def show_image(self, path):
        from PyQt6.QtGui import QPixmap
        import os

        if os.path.exists(path):
            pixmap = QPixmap(path)
            self.lbl_image.setPixmap(pixmap)
        else:
            self.lbl_image.setText("Image Not Found")

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
        self.reorder_input.setValue(float(self.product.reorder_point))
        self.preferred_qty_input.setValue(float(self.product.preferred_qty))
        self.weighted_check.setChecked(self.product.is_weighted)
        self.service_check.setChecked(self.product.is_service)

        # Load unit
        if self.product.unit_id:
            idx = self.unit_combo.findData(self.product.unit_id)
            if idx >= 0:
                self.unit_combo.setCurrentIndex(idx)

        # Load supplier
        if hasattr(self.product, "default_supplier_id") and self.product.default_supplier_id:
            idx = self.supplier_combo.findData(self.product.default_supplier_id)
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)

        if self.product.image_path:
            import os

            full_path = os.path.join(os.getcwd(), "cbpos", "assets", self.product.image_path)
            self.show_image(full_path)
            self.current_image_path = self.product.image_path

        # Load components
        db = Database()
        with db.get_session() as session:
            stmt = select(CompositeItem).where(CompositeItem.parent_product_id == self.product.id)
            components = session.scalars(stmt).all()

            for comp in components:
                row = self.comp_table.rowCount()
                self.comp_table.insertRow(row)
                self.comp_table.setItem(row, 0, QTableWidgetItem(str(comp.child_product_id)))

                child = session.get(Product, comp.child_product_id)
                child_name = child.name_en if child else "Unknown"

                self.comp_table.setItem(row, 1, QTableWidgetItem(child_name))
                self.comp_table.setItem(row, 2, QTableWidgetItem(str(comp.qty)))

                remove_btn = QPushButton("Remove")
                target_row = row
                remove_btn.clicked.connect(lambda checked, r=target_row: self._remove_component(r))
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
            "reorder_point": Decimal(str(self.reorder_input.value())),
            "preferred_qty": Decimal(str(self.preferred_qty_input.value())),
            "default_supplier_id": self.supplier_combo.currentData(),
            "unit_id": self.unit_combo.currentData(),
            "is_weighted": self.weighted_check.isChecked(),
            "is_service": self.service_check.isChecked(),
            "image_path": getattr(self, "current_image_path", None),
            "is_active": True,
        }

        if not data["name_en"]:
            QMessageBox.warning(self, "Validation", "Product name is required.")
            self.tabs.setCurrentIndex(0)
            self.name_en_input.setFocus()
            return

        if not data["barcode"]:
            QMessageBox.warning(self, "Validation", "Barcode is required.")
            self.tabs.setCurrentIndex(0)
            self.barcode_input.setFocus()
            return

        if data["price"] <= 0:
            QMessageBox.warning(self, "Validation", "Selling price must be greater than 0.")
            self.tabs.setCurrentIndex(0)
            self.price_input.setFocus()
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
                    QMessageBox.warning(self, "Duplicate", "A product with this barcode already exists.")
                    self.tabs.setCurrentIndex(0)
                    self.barcode_input.setFocus()
                    return
                self.inventory_service.create_product(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
