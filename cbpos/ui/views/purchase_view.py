from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableView,
    QPushButton,
    QLabel,
    QLineEdit,
    QFormLayout,
    QDialog,
    QMessageBox,
    QComboBox,
    QDateEdit,
    QHeaderView,
    QAbstractItemView,
    QCompleter,
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QDate
from PyQt6.QtGui import QStandardItemModel, QStandardItem

from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.services.purchase_service import PurchaseService
from cbpos.core.services.product_service import ProductService


class SupplierTableModel(QAbstractTableModel):
    def __init__(self, suppliers):
        super().__init__()
        self.suppliers = suppliers
        self.headers = ["ID", "Company", "Contact", "Phone", "Tax No"]

    def rowCount(self, parent=None):
        return len(self.suppliers)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            supplier = self.suppliers[index.row()]
            if index.column() == 0:
                return str(supplier.id)
            if index.column() == 1:
                return supplier.company_name
            if index.column() == 2:
                return supplier.contact_person
            if index.column() == 3:
                return supplier.phone
            if index.column() == 4:
                return supplier.tax_number
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None


class SupplierDialog(QDialog):
    def __init__(self, parent=None, supplier=None):
        super().__init__(parent)
        self.setWindowTitle(
            "Add Supplier" if not supplier else "Edit Supplier",
        )
        self.supplier = supplier
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)

        self.company_input = QLineEdit()
        self.contact_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.tax_input = QLineEdit()
        self.details_input = QLineEdit()

        if self.supplier:
            self.company_input.setText(self.supplier.company_name)
            self.contact_input.setText(self.supplier.contact_person or "")
            self.phone_input.setText(self.supplier.phone or "")
            self.tax_input.setText(self.supplier.tax_number or "")
            self.details_input.setText(self.supplier.contact_details or "")

        layout.addRow("Company Name:", self.company_input)
        layout.addRow("Contact Person:", self.contact_input)
        layout.addRow("Phone:", self.phone_input)
        layout.addRow("Tax Number:", self.tax_input)
        layout.addRow("Details:", self.details_input)

        btn_box = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addRow(btn_box)

    def get_data(self):
        return {
            "company_name": self.company_input.text(),
            "contact_person": self.contact_input.text(),
            "phone": self.phone_input.text(),
            "tax_number": self.tax_input.text(),
            "contact_details": self.details_input.text(),
        }


class PurchaseView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.refresh_suppliers()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Suppliers
        self.supplier_tab = QWidget()
        self.setup_supplier_tab()
        self.tabs.addTab(self.supplier_tab, "Suppliers")

        # Tab 2: New GRN
        self.grn_tab = QWidget()
        self.setup_grn_tab()
        self.tabs.addTab(self.grn_tab, "New GRN")

    def setup_supplier_tab(self):
        layout = QVBoxLayout(self.supplier_tab)

        # Toolbar
        toolbar = QHBoxLayout()
        add_btn = QPushButton("Add Supplier")
        add_btn.clicked.connect(self.add_supplier)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_suppliers)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Table
        self.supplier_table = QTableView()
        self.supplier_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.supplier_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.supplier_table)

    def setup_grn_tab(self):
        layout = QVBoxLayout(self.grn_tab)

        # Header Form
        form_layout = QHBoxLayout()

        self.supplier_combo = QComboBox()
        self.invoice_input = QLineEdit()
        self.invoice_input.setPlaceholderText("Vendor Invoice #")
        self.date_input = QDateEdit(QDate.currentDate())

        form_layout.addWidget(QLabel("Supplier:"))
        form_layout.addWidget(self.supplier_combo)
        form_layout.addWidget(QLabel("Ref #:"))
        form_layout.addWidget(self.invoice_input)
        form_layout.addWidget(QLabel("Date:"))
        form_layout.addWidget(self.date_input)

        layout.addLayout(form_layout)

        # Product Search
        search_layout = QHBoxLayout()
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText("Scan Barcode or Type Product Name...")
        self.product_search.returnPressed.connect(self.add_product_to_grid)

        # Completer
        self.completer = QCompleter()
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.product_search.setCompleter(self.completer)

        search_layout.addWidget(QLabel("Add Product:"))
        search_layout.addWidget(self.product_search)
        layout.addLayout(search_layout)

        # Items Grid
        self.grn_model = QStandardItemModel(0, 5)
        self.grn_model.setHorizontalHeaderLabels(["ID", "Product Name", "Receive Qty", "Unit Cost", "Total"])

        self.grn_table = QTableView()
        self.grn_table.setModel(self.grn_model)
        self.grn_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.grn_table)

        # Footer
        footer_layout = QHBoxLayout()
        self.total_label = QLabel("Total Cost: 0.00")
        self.total_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        commit_btn = QPushButton("Commit Stock")
        commit_btn.setStyleSheet("background-color: #39FF14; color: black; font-weight: bold; padding: 10px;")
        commit_btn.clicked.connect(self.commit_grn)

        footer_layout.addStretch()
        footer_layout.addWidget(self.total_label)
        footer_layout.addWidget(commit_btn)
        layout.addLayout(footer_layout)

        # Data
        self.grn_items = []  # List of dicts

    def refresh_suppliers(self):
        self.suppliers = SupplierService.get_all_suppliers()
        self.supplier_table.setModel(SupplierTableModel(self.suppliers))

        # Update Combo
        self.supplier_combo.clear()
        for s in self.suppliers:
            self.supplier_combo.addItem(s.company_name, s.id)

    def add_supplier(self):
        dialog = SupplierDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            SupplierService.create_supplier(**data)
            self.refresh_suppliers()

    def add_product_to_grid(self):
        query = self.product_search.text()
        if not query:
            return

        products = ProductService.search(query)
        if not products:
            QMessageBox.warning(self, "Not Found", "Product not found.")
            return

        # For simplicity, pick first match or if exact match
        product = products[0]

        # Add to grid
        qty = Decimal("1.000")
        cost = product.cost  # Default to current cost

        self.grn_items.append({"product": product, "qty": qty, "cost": cost})

        row = self.grn_model.rowCount()
        self.grn_model.insertRow(row)
        self.grn_model.setItem(row, 0, QStandardItem(str(product.id)))
        self.grn_model.setItem(row, 1, QStandardItem(product.name_en))
        self.grn_model.setItem(row, 2, QStandardItem(str(qty)))
        self.grn_model.setItem(row, 3, QStandardItem(str(cost)))
        self.grn_model.setItem(row, 4, QStandardItem(str(qty * cost)))

        self.product_search.clear()
        self.update_total()

    def update_total(self):
        total = sum(item["qty"] * item["cost"] for item in self.grn_items)
        total_str = format(total, ".2f")
        self.total_label.setText(f"Total Cost: {total_str}")

    def set_user(self, user):
        self.user = user

    def commit_grn(self):
        supplier_id = self.supplier_combo.currentData()
        ref_no = self.invoice_input.text()

        if not supplier_id or not ref_no:
            QMessageBox.warning(self, "Error", "Please select Supplier and enter Reference #")
            return

        if not self.grn_items:
            QMessageBox.warning(self, "Error", "No items in GRN")
            return

        if not hasattr(self, "user") or not self.user:
            QMessageBox.warning(self, "Error", "User not logged in.")
            return

        try:
            # 1. Create Draft
            purchase = PurchaseService.create_purchase(
                supplier_id=supplier_id,
                reference_external=ref_no,
                user_id=self.user.id,
            )

            # 2. Prepare Items
            items_data = []
            for i in range(self.grn_model.rowCount()):
                # Read from table in case user edited
                prod_id = int(self.grn_model.item(i, 0).text())
                qty = Decimal(self.grn_model.item(i, 2).text())
                cost = Decimal(self.grn_model.item(i, 3).text())

                items_data.append({"product_id": prod_id, "qty": qty, "cost": cost})

            # 3. Commit
            PurchaseService.commit_purchase(purchase.id, items_data)

            QMessageBox.information(
                self,
                "Success",
                (f"GRN {purchase.document_number} " f"Committed Successfully!"),
            )

            # Reset
            self.grn_model.removeRows(0, self.grn_model.rowCount())
            self.grn_items = []
            self.invoice_input.clear()
            self.update_total()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
