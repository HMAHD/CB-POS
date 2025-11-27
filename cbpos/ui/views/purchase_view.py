from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QFormLayout,
    QLineEdit,
    QHeaderView,
    QComboBox,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
)
from decimal import Decimal
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.services.purchase_service import PurchaseService
from cbpos.core.services.product_service import ProductService
from cbpos.ui.resources.icons import Icons


class PurchaseView(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.user = None

        # Header
        lbl_title = QLabel("Purchasing & Receiving")
        lbl_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #00BCEB;")
        self.layout.addWidget(lbl_title)

        # Tabs
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        # Tab 1: Suppliers
        self.tab_suppliers = QWidget()
        self.init_suppliers_tab()
        self.tabs.addTab(self.tab_suppliers, "Suppliers")

        # Tab 2: Receive Stock (GRN)
        self.tab_receive = QWidget()
        self.init_receive_tab()
        self.tabs.addTab(self.tab_receive, "Receive Stock (GRN)")

    def init_suppliers_tab(self):
        layout = QVBoxLayout(self.tab_suppliers)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_add_supplier = QPushButton("Add Supplier")
        self.btn_add_supplier.setIcon(Icons.get(Icons.ADD))
        self.btn_add_supplier.clicked.connect(self.open_add_supplier_dialog)
        toolbar.addWidget(self.btn_add_supplier)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Table
        self.supplier_table = QTableWidget()
        self.supplier_table.setColumnCount(5)
        self.supplier_table.setHorizontalHeaderLabels(
            ["ID", "Company", "Contact", "Phone", "Status"]
        )
        self.supplier_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.supplier_table)

        self.load_suppliers()

    def load_suppliers(self):
        self.supplier_table.setRowCount(0)
        suppliers = SupplierService.get_all_suppliers(active_only=False)
        for s in suppliers:
            row = self.supplier_table.rowCount()
            self.supplier_table.insertRow(row)
            self.supplier_table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self.supplier_table.setItem(row, 1, QTableWidgetItem(s.company_name))
            self.supplier_table.setItem(
                row, 2, QTableWidgetItem(s.contact_person or "")
            )
            self.supplier_table.setItem(row, 3, QTableWidgetItem(s.phone or ""))
            status = "Active" if s.is_active else "Inactive"
            self.supplier_table.setItem(row, 4, QTableWidgetItem(status))

    def open_add_supplier_dialog(self):
        dialog = SupplierDialog(self)
        if dialog.exec():
            self.load_suppliers()
            self.load_supplier_combo()  # Refresh combo in other tab

    def init_receive_tab(self):
        layout = QVBoxLayout(self.tab_receive)

        # Form
        form_layout = QHBoxLayout()

        self.combo_supplier = QComboBox()
        self.load_supplier_combo()
        form_layout.addWidget(QLabel("Supplier:"))
        form_layout.addWidget(self.combo_supplier)

        self.txt_invoice = QLineEdit()
        self.txt_invoice.setPlaceholderText("Invoice / Ref No")
        form_layout.addWidget(QLabel("Reference:"))
        form_layout.addWidget(self.txt_invoice)

        layout.addLayout(form_layout)

        # Product Entry
        entry_layout = QHBoxLayout()
        self.txt_barcode = QLineEdit()
        self.txt_barcode.setPlaceholderText("Scan Barcode or Type ID")
        self.txt_barcode.returnPressed.connect(self.add_product_to_grid)
        entry_layout.addWidget(QLabel("Product:"))
        entry_layout.addWidget(self.txt_barcode)

        self.spin_qty = QDoubleSpinBox()
        self.spin_qty.setRange(0.001, 99999)
        self.spin_qty.setDecimals(3)
        entry_layout.addWidget(QLabel("Qty:"))
        entry_layout.addWidget(self.spin_qty)

        self.spin_cost = QDoubleSpinBox()
        self.spin_cost.setRange(0, 999999)
        self.spin_cost.setDecimals(2)
        entry_layout.addWidget(QLabel("Unit Cost:"))
        entry_layout.addWidget(self.spin_cost)

        btn_add = QPushButton("Add Line")
        btn_add.clicked.connect(self.add_product_to_grid)
        entry_layout.addWidget(btn_add)

        layout.addLayout(entry_layout)

        # Grid
        self.grn_table = QTableWidget()
        self.grn_table.setColumnCount(5)
        self.grn_table.setHorizontalHeaderLabels(
            ["ID", "Product Name", "Qty", "Unit Cost", "Total"]
        )
        self.grn_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.grn_table)

        # Footer
        footer = QHBoxLayout()
        self.lbl_total = QLabel("Total: 0.00")
        self.lbl_total.setStyleSheet("font-size: 18px; font-weight: bold;")
        footer.addWidget(self.lbl_total)
        footer.addStretch()

        btn_commit = QPushButton("COMMIT STOCK")
        btn_commit.setStyleSheet(
            "background-color: #39FF14; color: black; font-weight: bold; padding: 10px;"
        )
        btn_commit.clicked.connect(self.commit_grn)
        footer.addWidget(btn_commit)

        layout.addLayout(footer)

    def load_supplier_combo(self):
        self.combo_supplier.clear()
        suppliers = SupplierService.get_all_suppliers()
        for s in suppliers:
            self.combo_supplier.addItem(s.company_name, s.id)

    def add_product_to_grid(self):
        barcode = self.txt_barcode.text().strip()
        qty = self.spin_qty.value()
        cost = self.spin_cost.value()

        if not barcode or qty <= 0:
            return

        # Find product
        product = ProductService.get_product_by_barcode(barcode)
        if not product:
            # Try by ID
            if barcode.isdigit():
                product = ProductService.get_product_by_id(int(barcode))

        if not product:
            QMessageBox.warning(self, "Error", "Product not found")
            return

        # Add to table
        row = self.grn_table.rowCount()
        self.grn_table.insertRow(row)
        self.grn_table.setItem(row, 0, QTableWidgetItem(str(product.id)))
        self.grn_table.setItem(row, 1, QTableWidgetItem(product.name_en))
        self.grn_table.setItem(row, 2, QTableWidgetItem(f"{qty:.3f}"))  # noqa: E231
        self.grn_table.setItem(row, 3, QTableWidgetItem(f"{cost:.2f}"))  # noqa: E231
        self.grn_table.setItem(
            row, 4, QTableWidgetItem(f"{qty * cost:.2f}")  # noqa: E231
        )

        self.update_total()
        self.txt_barcode.clear()
        self.spin_qty.setValue(0)
        self.spin_cost.setValue(0)
        self.txt_barcode.setFocus()

    def update_total(self):
        total = Decimal(0)
        for r in range(self.grn_table.rowCount()):
            val = Decimal(self.grn_table.item(r, 4).text())
            total += val
        self.lbl_total.setText(f"Total: {total:.2f}")  # noqa: E231

    def commit_grn(self):
        supplier_id = self.combo_supplier.currentData()
        ref_no = self.txt_invoice.text().strip()

        if not supplier_id:
            QMessageBox.warning(self, "Error", "Select a supplier")
            return
        if not ref_no:
            QMessageBox.warning(self, "Error", "Enter reference number")
            return
        if self.grn_table.rowCount() == 0:
            QMessageBox.warning(self, "Error", "No items to receive")
            return

        items = []
        for r in range(self.grn_table.rowCount()):
            pid = int(self.grn_table.item(r, 0).text())
            qty = Decimal(self.grn_table.item(r, 2).text())
            cost = Decimal(self.grn_table.item(r, 3).text())
            items.append((pid, qty, cost))

        try:
            # 1. Create Draft
            purchase = PurchaseService.create_purchase(supplier_id, ref_no, items)

            # 2. Commit
            if not self.user:
                QMessageBox.warning(self, "Error", "User not logged in")
                return

            PurchaseService.commit_purchase(purchase.id, self.user.id)

            QMessageBox.information(self, "Success", "Stock Received Successfully!")
            self.grn_table.setRowCount(0)
            self.txt_invoice.clear()
            self.update_total()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def set_user(self, user):
        self.user = user


class SupplierDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Supplier")
        self.setModal(True)
        self.resize(400, 300)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.txt_company = QLineEdit()
        self.txt_contact = QLineEdit()
        self.txt_phone = QLineEdit()
        self.txt_email = QLineEdit()
        self.txt_tax = QLineEdit()

        form.addRow("Company Name *", self.txt_company)
        form.addRow("Contact Person", self.txt_contact)
        form.addRow("Phone", self.txt_phone)
        form.addRow("Email", self.txt_email)
        form.addRow("Tax / VAT No", self.txt_tax)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        name = self.txt_company.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Company Name is required")
            return

        try:
            SupplierService.create_supplier(
                company_name=name,
                contact_person=self.txt_contact.text().strip(),
                phone=self.txt_phone.text().strip(),
                email=self.txt_email.text().strip(),
                tax_number=self.txt_tax.text().strip(),
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
