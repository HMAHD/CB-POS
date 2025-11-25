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
)
from cbpos.core.models import Product, Category
from cbpos.core.database import Database


class ProductEditorDialog(QDialog):
    def __init__(self, product: Product = None, parent=None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle("Edit Product" if product else "New Product")
        self.setMinimumWidth(400)
        self.setup_ui()
        if product:
            self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
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

        form.addRow("Barcode:", self.barcode_input)
        form.addRow("Name (EN):", self.name_en_input)
        form.addRow("Name (SI):", self.name_si_input)
        form.addRow("Price (MRP):", self.price_input)
        form.addRow("Cost:", self.cost_input)
        form.addRow("Stock Qty:", self.stock_input)
        form.addRow("", self.weighted_check)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_product)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_data(self):
        self.barcode_input.setText(self.product.barcode)
        self.name_en_input.setText(self.product.name_en)
        self.name_si_input.setText(self.product.name_si or "")
        self.price_input.setValue(float(self.product.price))
        self.cost_input.setValue(float(self.product.cost))
        self.stock_input.setValue(float(self.product.stock_qty))
        self.weighted_check.setChecked(self.product.is_weighted)
        self.barcode_input.setReadOnly(True)  # Prevent changing barcode for now

    def save_product(self):
        barcode = self.barcode_input.text().strip()
        name_en = self.name_en_input.text().strip()
        price = Decimal(str(self.price_input.value()))
        cost = Decimal(str(self.cost_input.value()))
        stock = Decimal(str(self.stock_input.value()))

        if not barcode or not name_en:
            QMessageBox.warning(self, "Error", "Barcode and English Name are required.")
            return

        db = Database()
        session = db.SessionLocal()
        try:
            if self.product:
                # Update
                prod = session.query(Product).get(self.product.id)
                prod.name_en = name_en
                prod.name_si = self.name_si_input.text().strip()
                prod.price = price
                prod.cost = cost
                prod.stock_qty = stock
                prod.is_weighted = self.weighted_check.isChecked()
            else:
                # Create
                # Assign to first category for now (TODO: Add Category Selector)
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
                    category_id=cat.id,
                )
                session.add(new_prod)

            session.commit()
            self.accept()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()
