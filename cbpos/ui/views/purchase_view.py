from datetime import datetime
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
    QTableWidget,
    QTableWidgetItem,
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QDate
from PyQt6.QtGui import QStandardItemModel, QStandardItem

from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.services.purchase_service import PurchaseService
from cbpos.core.services.product_service import ProductService
from cbpos.core.utils.formatters import format_currency


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


class PurchaseHistoryModel(QAbstractTableModel):
    """Table model for GRN history list."""

    HEADERS = ["GRN #", "Date", "Supplier", "Ref #", "Items", "Total Cost", "Status"]

    def __init__(self, purchases=None):
        super().__init__()
        self.purchases = purchases or []

    def rowCount(self, parent=None):
        return len(self.purchases)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def data(self, index, role):
        if not index.isValid():
            return None
        purchase = self.purchases[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return purchase.document_number
            if col == 1:
                return purchase.date.strftime("%Y-%m-%d %H:%M") if purchase.date else ""
            if col == 2:
                return purchase.supplier.company_name if purchase.supplier else ""
            if col == 3:
                return purchase.reference_external or ""
            if col == 4:
                return str(len(purchase.items)) if purchase.items else "0"
            if col == 5:
                return format_currency(purchase.total_cost)
            if col == 6:
                return purchase.status
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (4, 5):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def get_purchase(self, row: int):
        """Get purchase object at given row."""
        if 0 <= row < len(self.purchases):
            return self.purchases[row]
        return None


class GRNDetailDialog(QDialog):
    """Read-only detail view of a completed GRN."""

    def __init__(self, purchase_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GRN Details")
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        self.init_ui(purchase_id)

    def init_ui(self, purchase_id: int) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        purchase = PurchaseService.get_purchase(purchase_id)
        if not purchase:
            layout.addWidget(QLabel("Purchase not found."))
            return

        # Header
        title = QLabel(f"GRN: {purchase.document_number}")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Info row
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(f"Supplier: {purchase.supplier.company_name if purchase.supplier else 'N/A'}"))
        info_layout.addWidget(QLabel(f"Ref #: {purchase.reference_external or 'N/A'}"))
        info_layout.addWidget(QLabel(f"Date: {purchase.date.strftime('%Y-%m-%d %H:%M') if purchase.date else 'N/A'}"))
        info_layout.addWidget(QLabel(f"Status: {purchase.status}"))
        info_layout.addStretch()
        layout.addLayout(info_layout)

        # Items table
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Product", "Barcode", "Qty", "Unit Cost", "Line Total"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for item in purchase.items:
            row = table.rowCount()
            table.insertRow(row)
            product_name = item.product.name_en if item.product else "Unknown"
            barcode = item.product.barcode if item.product else ""
            line_total = item.qty_received * item.unit_cost

            table.setItem(row, 0, QTableWidgetItem(product_name))
            table.setItem(row, 1, QTableWidgetItem(barcode))

            qty_item = QTableWidgetItem(f"{item.qty_received:.3f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 2, qty_item)

            cost_item = QTableWidgetItem(format_currency(item.unit_cost))
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 3, cost_item)

            total_item = QTableWidgetItem(format_currency(line_total))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 4, total_item)

        layout.addWidget(table, 1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        total_label = QLabel(f"Total Cost: {format_currency(purchase.total_cost)}")
        total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        footer.addWidget(total_label)
        layout.addLayout(footer)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


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

        # Tab 3: GRN History
        self.history_tab = QWidget()
        self.setup_history_tab()
        self.tabs.addTab(self.history_tab, "GRN History")

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

    def setup_history_tab(self) -> None:
        """Setup the GRN History tab with filters and table."""
        layout = QVBoxLayout(self.history_tab)

        # Filters bar
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Supplier:"))
        self.history_supplier_combo = QComboBox()
        self.history_supplier_combo.addItem("All Suppliers", None)
        filter_layout.addWidget(self.history_supplier_combo)

        filter_layout.addWidget(QLabel("Status:"))
        self.history_status_combo = QComboBox()
        self.history_status_combo.addItem("All", None)
        self.history_status_combo.addItem("Completed", "COMPLETED")
        self.history_status_combo.addItem("Draft", "DRAFT")
        self.history_status_combo.addItem("Void", "VOID")
        filter_layout.addWidget(self.history_status_combo)

        filter_layout.addWidget(QLabel("From:"))
        self.history_date_from = QDateEdit()
        self.history_date_from.setCalendarPopup(True)
        self.history_date_from.setDate(QDate.currentDate().addMonths(-3))
        filter_layout.addWidget(self.history_date_from)

        filter_layout.addWidget(QLabel("To:"))
        self.history_date_to = QDateEdit()
        self.history_date_to.setCalendarPopup(True)
        self.history_date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.history_date_to)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("class", "primary")
        refresh_btn.clicked.connect(self.refresh_history)
        filter_layout.addWidget(refresh_btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Table
        self.history_model = PurchaseHistoryModel()
        self.history_table = QTableView()
        self.history_table.setModel(self.history_model)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.doubleClicked.connect(self.on_history_double_click)
        layout.addWidget(self.history_table, 1)

    def refresh_history(self) -> None:
        """Refresh the GRN history table with current filters."""
        supplier_id = self.history_supplier_combo.currentData()
        status = self.history_status_combo.currentData()

        qd_from = self.history_date_from.date()
        date_from = datetime(qd_from.year(), qd_from.month(), qd_from.day())

        qd_to = self.history_date_to.date()
        date_to = datetime(qd_to.year(), qd_to.month(), qd_to.day(), 23, 59, 59)

        purchases = PurchaseService.get_all_purchases(
            status=status,
            supplier_id=supplier_id,
            date_from=date_from,
            date_to=date_to,
        )

        self.history_model = PurchaseHistoryModel(purchases)
        self.history_table.setModel(self.history_model)

    def on_history_double_click(self, index) -> None:
        """Open GRN detail dialog on double-click."""
        purchase = self.history_model.get_purchase(index.row())
        if purchase:
            dialog = GRNDetailDialog(purchase.id, self)
            dialog.exec()

    def refresh_suppliers(self):
        self.suppliers = SupplierService.get_all_suppliers()
        self.supplier_table.setModel(SupplierTableModel(self.suppliers))

        # Update GRN Combo
        self.supplier_combo.clear()
        for s in self.suppliers:
            self.supplier_combo.addItem(s.company_name, s.id)

        # Update History Combo
        if hasattr(self, "history_supplier_combo"):
            current_data = self.history_supplier_combo.currentData()
            self.history_supplier_combo.clear()
            self.history_supplier_combo.addItem("All Suppliers", None)
            for s in self.suppliers:
                self.history_supplier_combo.addItem(s.company_name, s.id)
            # Restore selection
            if current_data:
                for i in range(self.history_supplier_combo.count()):
                    if self.history_supplier_combo.itemData(i) == current_data:
                        self.history_supplier_combo.setCurrentIndex(i)
                        break

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
