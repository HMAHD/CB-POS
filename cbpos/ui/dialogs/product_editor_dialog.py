from decimal import Decimal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QDialogButtonBox,
    QCheckBox,
    QMessageBox,
    QTabWidget,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QHeaderView,
)
from PyQt6.QtCore import Qt
from cbpos.core.models import Product, Category, CompositeItem
from cbpos.core.database import Database
from cbpos.core.services.product_service import ProductService


class ProductEditorDialog(QDialog):
    def __init__(self, product: Product = None, parent=None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle("Edit Product" if product else "New Product")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        # Store composition changes
        self.composition_data = []  # List of {'child_id': int, 'qty': Decimal}

        self.setup_ui()
        if product:
            self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tabs = QTabWidget()

        # Tab 1: Basic Information
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        form = QFormLayout()

        self.barcode_input = QLineEdit()
        self.name_en_input = QLineEdit()
        self.name_si_input = QLineEdit()

        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 1000000)
        self.price_input.setDecimals(2)

        self.cost_input = QDoubleSpinBox()
        self.cost_input.setRange(0, 1000000)
        self.cost_input.setDecimals(2)

        self.stock_input = QDoubleSpinBox()
        self.stock_input.setRange(-1000, 1000000)
        self.stock_input.setDecimals(3)

        self.weighted_check = QCheckBox("Is Weighted Item?")
        self.composite_check = QCheckBox("Is Composite/Bundle Product?")
        self.composite_check.stateChanged.connect(self.on_composite_changed)

        form.addRow("Barcode:", self.barcode_input)
        form.addRow("Name (EN):", self.name_en_input)
        form.addRow("Name (SI):", self.name_si_input)
        form.addRow("Price (MRP):", self.price_input)
        form.addRow("Cost:", self.cost_input)
        form.addRow("Stock Qty:", self.stock_input)
        form.addRow("", self.weighted_check)
        form.addRow("", self.composite_check)

        basic_layout.addLayout(form)
        self.tabs.addTab(basic_tab, "Basic Information")

        # Tab 2: Composition (for composite products)
        self.composition_tab = QWidget()
        comp_layout = QVBoxLayout(self.composition_tab)

        # Header label
        header = QLabel("Bundle Components:")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        comp_layout.addWidget(header)

        # Component table
        self.component_table = QTableWidget()
        self.component_table.setColumnCount(4)
        self.component_table.setHorizontalHeaderLabels(
            ["Child Product", "Barcode", "Quantity", ""]
        )
        self.component_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.component_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.component_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.component_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.component_table.verticalHeader().setVisible(False)
        comp_layout.addWidget(self.component_table)

        # Add component section
        add_section = QHBoxLayout()
        add_label = QLabel("Add Component:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search product by barcode or name...")
        self.qty_input = QDoubleSpinBox()
        self.qty_input.setRange(0.001, 1000)
        self.qty_input.setDecimals(3)
        self.qty_input.setValue(1.0)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_component)

        add_section.addWidget(add_label)
        add_section.addWidget(self.search_input, 1)
        add_section.addWidget(QLabel("Qty:"))
        add_section.addWidget(self.qty_input)
        add_section.addWidget(add_btn)

        comp_layout.addLayout(add_section)

        # Info label
        info = QLabel(
            "Note: When this bundle is sold, the quantities of child products will be deducted automatically."
        )
        info.setStyleSheet("color: #00BCEB; font-size: 11px;")
        info.setWordWrap(True)
        comp_layout.addWidget(info)

        self.tabs.addTab(self.composition_tab, "Composition")
        self.tabs.setTabEnabled(1, False)  # Disabled by default

        layout.addWidget(self.tabs)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_product)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def on_composite_changed(self, state):
        """Enable/disable composition tab based on checkbox"""
        is_composite = state == Qt.CheckState.Checked.value
        self.tabs.setTabEnabled(1, is_composite)
        if is_composite:
            self.tabs.setCurrentIndex(1)

    def add_component(self):
        """Add a component to the composition"""
        search_term = self.search_input.text().strip()
        if not search_term:
            QMessageBox.warning(
                self, "Error", "Please enter a product barcode or name."
            )
            return

        # Search for product
        products = ProductService.search_products(search_term)

        if not products:
            QMessageBox.warning(
                self, "Error", f"No product found matching '{search_term}'."
            )
            return

        if len(products) > 1:
            QMessageBox.warning(
                self,
                "Multiple Results",
                f"Found {len(products)} products. Please be more specific.",
            )
            return

        child_product = products[0]
        qty = Decimal(str(self.qty_input.value()))

        # Check if already added
        for comp in self.composition_data:
            if comp["child_id"] == child_product.id:
                QMessageBox.warning(
                    self,
                    "Duplicate",
                    f"{child_product.name_en} is already in the composition.",
                )
                return

        # Add to data and table
        self.composition_data.append(
            {
                "child_id": child_product.id,
                "child_name": child_product.name_en,
                "child_barcode": child_product.barcode,
                "qty": qty,
            }
        )

        self.refresh_component_table()

        # Clear inputs
        self.search_input.clear()
        self.qty_input.setValue(1.0)

    def remove_component(self, child_id):
        """Remove a component from the composition"""
        self.composition_data = [
            c for c in self.composition_data if c["child_id"] != child_id
        ]
        self.refresh_component_table()

    def refresh_component_table(self):
        """Refresh the component table display"""
        self.component_table.setRowCount(0)

        for row, comp in enumerate(self.composition_data):
            self.component_table.insertRow(row)

            # Product name
            self.component_table.setItem(row, 0, QTableWidgetItem(comp["child_name"]))

            # Barcode
            remove_btn = QPushButton("Remove")
            remove_btn.clicked.connect(
                lambda checked, cid=comp["child_id"]: self.remove_component(cid)
            )
            remove_btn.setStyleSheet("background-color: #FF4136; color: white;")
            self.component_table.setCellWidget(row, 3, remove_btn)

    def load_data(self):
        """Load product data into form"""
        self.barcode_input.setText(self.product.barcode)
        self.name_en_input.setText(self.product.name_en)
        self.name_si_input.setText(self.product.name_si or "")
        self.price_input.setValue(float(self.product.price))
        self.cost_input.setValue(float(self.product.cost))
        self.stock_input.setValue(float(self.product.stock_qty))
        self.weighted_check.setChecked(self.product.is_weighted)
        self.composite_check.setChecked(self.product.is_composite)
        self.barcode_input.setReadOnly(True)  # Prevent changing barcode

        # Load composition data if composite
        if self.product.is_composite:
            db = Database()
            with db.get_session() as session:
                components = (
                    session.query(CompositeItem)
                    .filter(CompositeItem.parent_product_id == self.product.id)
                    .all()
                )

                for comp in components:
                    child = session.query(Product).get(comp.child_product_id)
                    if child:
                        self.composition_data.append(
                            {
                                "child_id": child.id,
                                "child_name": child.name_en,
                                "child_barcode": child.barcode,
                                "qty": comp.qty,
                            }
                        )

            self.refresh_component_table()

    def save_product(self):
        """Save product and composition data"""
        barcode = self.barcode_input.text().strip()
        name_en = self.name_en_input.text().strip()
        price = Decimal(str(self.price_input.value()))
        cost = Decimal(str(self.cost_input.value()))
        stock = Decimal(str(self.stock_input.value()))
        is_composite = self.composite_check.isChecked()

        if not barcode or not name_en:
            QMessageBox.warning(self, "Error", "Barcode and English Name are required.")
            return

        # Validate composition for composite products
        if is_composite and not self.composition_data:
            QMessageBox.warning(
                self, "Error", "Composite products must have at least one component."
            )
            return

        db = Database()
        session = db.SessionLocal()
        try:
            if self.product:
                # Update existing product
                prod = session.query(Product).get(self.product.id)
                prod.name_en = name_en
                prod.name_si = self.name_si_input.text().strip()
                prod.price = price
                prod.cost = cost
                prod.stock_qty = stock
                prod.is_weighted = self.weighted_check.isChecked()
                prod.is_composite = is_composite

                # Update composition
                # Delete existing compositions
                session.query(CompositeItem).filter(
                    CompositeItem.parent_product_id == prod.id
                ).delete()

                # Add new compositions
                if is_composite:
                    for comp in self.composition_data:
                        new_comp = CompositeItem(
                            parent_product_id=prod.id,
                            child_product_id=comp["child_id"],
                            qty=comp["qty"],
                        )
                        session.add(new_comp)
            else:
                # Create new product
                cat = session.query(Category).first()
                if not cat:
                    QMessageBox.warning(
                        self, "Error", "No categories found. Please seed DB."
                    )
                    return

                new_prod = Product(
                    barcode=barcode,
                    name_en=name_en,
                    name_si=self.name_si_input.text().strip(),
                    price=price,
                    cost=cost,
                    stock_qty=stock,
                    is_weighted=self.weighted_check.isChecked(),
                    is_composite=is_composite,
                    category_id=cat.id,
                )
                session.add(new_prod)
                session.flush()  # Get the ID

                # Add compositions
                if is_composite:
                    for comp in self.composition_data:
                        new_comp = CompositeItem(
                            parent_product_id=new_prod.id,
                            child_product_id=comp["child_id"],
                            qty=comp["qty"],
                        )
                        session.add(new_comp)

            session.commit()
            self.accept()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()
