import logging
from decimal import Decimal

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QComboBox,
    QCompleter,
)
from PyQt6.QtCore import Qt, QStringListModel

from cbpos.core.services.product_service import ProductService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.proforma_service import ProformaService
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)


class ProformaDialog(QDialog):
    """Dialog for creating a new Proforma / Quotation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Quotation")
        self.setMinimumSize(700, 550)
        self.items: list[dict] = []
        self.products_cache: dict = {}
        self.init_ui()
        self.load_products()
        self.load_customers()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header Section
        form = QFormLayout()

        self.customer_combo = QComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.addItem("-- No Customer --", None)
        form.addRow("Customer:", self.customer_combo)

        self.validity_spin = QSpinBox()
        self.validity_spin.setRange(1, 365)
        self.validity_spin.setValue(30)
        self.validity_spin.setSuffix(" days")
        form.addRow("Validity:", self.validity_spin)

        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.setPlaceholderText("Optional notes...")
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        # Product Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Add Product:"))
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText("Search by name or barcode...")
        self.product_completer = QCompleter()
        self.product_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.product_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.product_search.setCompleter(self.product_completer)
        self.product_search.returnPressed.connect(self.add_product)
        search_layout.addWidget(self.product_search, 1)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_product)
        search_layout.addWidget(add_btn)

        layout.addLayout(search_layout)

        # Items Grid
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(6)
        self.items_table.setHorizontalHeaderLabels(["Product", "Qty", "Unit Price", "Disc Type", "Disc Value", "Total"])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items_table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.items_table)

        # Footer: Total + Create
        footer = QHBoxLayout()

        self.total_label = QLabel(f"<b>Total: {format_currency(0)}</b>")
        self.total_label.setStyleSheet("font-size: 16px;")
        footer.addWidget(self.total_label)

        footer.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        create_btn = QPushButton("Create Quotation")
        create_btn.setStyleSheet("background-color: #00BCEB; color: white; font-weight: bold; padding: 8px 20px;")
        create_btn.clicked.connect(self.create_proforma)
        footer.addWidget(create_btn)

        layout.addLayout(footer)

    def load_products(self) -> None:
        """Load products for the completer."""
        products = ProductService().get_all_products()
        names = []
        for p in products:
            key = f"{p.name_en} [{p.barcode}]"
            names.append(key)
            self.products_cache[key] = p
            self.products_cache[p.barcode] = p

        model = QStringListModel(names)
        self.product_completer.setModel(model)

    def load_customers(self) -> None:
        """Load customers into the combo box."""
        customers = CustomerService().get_all_customers()
        for c in customers:
            self.customer_combo.addItem(c.name, c.id)

    def add_product(self) -> None:
        """Add selected product to items grid."""
        text = self.product_search.text().strip()
        if not text:
            return

        product = self.products_cache.get(text)
        if not product:
            # Try barcode lookup
            for key, p in self.products_cache.items():
                if hasattr(p, "barcode") and p.barcode == text:
                    product = p
                    break

        if not product:
            QMessageBox.warning(self, "Not Found", f"Product '{text}' not found.")
            return

        # Check if already in items
        for item in self.items:
            if item["product_id"] == product.id:
                item["quantity"] += Decimal("1.000")
                item["line_total"] = item["quantity"] * item["unit_price"]
                self.refresh_table()
                self.product_search.clear()
                return

        self.items.append(
            {
                "product_id": product.id,
                "product_name": product.name_en,
                "quantity": Decimal("1.000"),
                "unit_price": product.price,
                "discount_type": "NONE",
                "discount_value": Decimal("0.00"),
                "line_total": product.price,
            }
        )
        self.refresh_table()
        self.product_search.clear()

    def refresh_table(self) -> None:
        """Refresh items table and total."""
        self.items_table.setRowCount(0)
        total = Decimal("0.00")

        for row, item in enumerate(self.items):
            self.items_table.insertRow(row)

            self.items_table.setItem(row, 0, QTableWidgetItem(item["product_name"]))

            qty_item = QTableWidgetItem(f"{item['quantity']:.3f}")  # noqa: E231
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, 1, qty_item)

            price_item = QTableWidgetItem(f"{item['unit_price']:.2f}")  # noqa: E231
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, 2, price_item)

            self.items_table.setItem(row, 3, QTableWidgetItem(item["discount_type"]))

            disc_item = QTableWidgetItem(f"{item['discount_value']:.2f}")  # noqa: E231
            disc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, 4, disc_item)

            line_total = item["line_total"]
            total_item = QTableWidgetItem(format_currency(line_total))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, 5, total_item)

            total += line_total

        self.total_label.setText(f"<b>Total: {format_currency(total)}</b>")

    def show_context_menu(self, position) -> None:
        """Show context menu for editing/removing items."""
        if self.items_table.rowCount() == 0:
            return

        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        edit_qty = menu.addAction("Change Quantity")
        remove = menu.addAction("Remove Item")

        action = menu.exec(self.items_table.viewport().mapToGlobal(position))
        row = self.items_table.currentRow()
        if row < 0:
            return

        if action == edit_qty:
            self.edit_item_qty(row)
        elif action == remove:
            del self.items[row]
            self.refresh_table()

    def edit_item_qty(self, row: int) -> None:
        """Edit quantity of an item via input dialog."""
        from PyQt6.QtWidgets import QInputDialog

        current = float(self.items[row]["quantity"])
        qty, ok = QInputDialog.getDouble(self, "Change Quantity", "New quantity:", current, 0.001, 99999.0, 3)
        if ok:
            self.items[row]["quantity"] = Decimal(str(qty))
            self.items[row]["line_total"] = self.items[row]["quantity"] * self.items[row]["unit_price"]
            self.refresh_table()

    def create_proforma(self) -> None:
        """Create the proforma via ProformaService."""
        if not self.items:
            QMessageBox.warning(self, "No Items", "Add at least one item to the quotation.")
            return

        customer_id = self.customer_combo.currentData()
        validity = self.validity_spin.value()
        notes = self.notes_edit.toPlainText().strip() or None

        proforma = ProformaService.create_proforma(
            items=self.items,
            customer_id=customer_id,
            validity_days=validity,
            notes=notes,
        )

        if proforma:
            QMessageBox.information(
                self,
                "Success",
                f"Quotation <b>{proforma.document_number}</b> created successfully.",
            )
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to create quotation. Check logs.")
