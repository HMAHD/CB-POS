"""
Dialog for selecting products and printing barcode labels.
"""

import logging
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QMessageBox,
    QCompleter,
)
from PyQt6.QtCore import Qt, QStringListModel
from PyQt6.QtGui import QIntValidator
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.label_service import LabelService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)

TABLE_ROW_HEIGHT = 44


class LabelPrintDialog(QDialog):
    """Dialog to search products, set quantities, and print barcode labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Print Barcode Labels")
        self.setMinimumSize(700, 500)
        self.setObjectName("LabelPrintDialog")
        self.product_service = ProductService()
        self.label_items = []  # List of {'product': Product, 'quantity': int}
        self.products_cache: dict = {}
        self._completer_activated = False
        self._init_ui()
        self._load_products()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Search bar with autocomplete
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search product by name or barcode...")

        self.product_completer = QCompleter()
        self.product_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.product_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.product_completer.setMaxVisibleItems(10)
        self.search_input.setCompleter(self.product_completer)

        # Connect completer activated (user picked from dropdown)
        self.product_completer.activated.connect(self._on_completer_activated)
        self.search_input.returnPressed.connect(self._on_return_pressed)
        search_layout.addWidget(self.search_input, 1)

        btn_add = QPushButton("Add")
        btn_add.setProperty("class", "primary")
        btn_add.clicked.connect(self._add_product)
        search_layout.addWidget(btn_add)

        layout.addLayout(search_layout)

        # Label queue table
        self.table = QTableWidget()
        self.table.setObjectName("LabelQueueTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Product", "Barcode", "Price", "Qty"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(3, 80)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Summary + actions
        btn_layout = QHBoxLayout()

        self.lbl_total = QLabel("Total labels: 0")
        self.lbl_total.setProperty("class", "bold")
        btn_layout.addWidget(self.lbl_total)

        btn_layout.addStretch()

        btn_remove = QPushButton("Remove Selected")
        btn_remove.clicked.connect(self._remove_selected)
        btn_layout.addWidget(btn_remove)

        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self._clear_all)
        btn_layout.addWidget(btn_clear)

        btn_preview = QPushButton("Preview Label")
        btn_preview.clicked.connect(self._preview_label)
        btn_layout.addWidget(btn_preview)

        btn_print = QPushButton("Print Labels")
        btn_print.setProperty("class", "primary")
        btn_print.clicked.connect(self._print_labels)
        btn_layout.addWidget(btn_print)

        layout.addLayout(btn_layout)

    def _load_products(self) -> None:
        """Load all active products into cache and completer."""
        products = self.product_service.get_all_products()
        names = []
        for p in products:
            key = f"{p.name_en} [{p.barcode}]"
            names.append(key)
            self.products_cache[key] = p
            self.products_cache[p.barcode] = p

        model = QStringListModel(names)
        self.product_completer.setModel(model)

    def _on_completer_activated(self, text: str) -> None:
        """Called when user selects an item from the completer dropdown."""
        self._completer_activated = True
        self.search_input.setText(text)
        self._add_product()

    def _on_return_pressed(self) -> None:
        """Handle Enter key — skip if completer just activated (already handled)."""
        if self._completer_activated:
            self._completer_activated = False
            return
        self._add_product()

    def _add_product(self) -> None:
        """Search for product and add to label queue."""
        query = self.search_input.text().strip()
        if not query:
            return

        # Check cache first (exact match from completer or barcode)
        product = self.products_cache.get(query)

        if not product:
            # Fall back to service search
            products = self.product_service.search_products(query, mode="ALL")

            if not products:
                QMessageBox.warning(
                    self, "Not Found", f"No product found for '{query}'."
                )
                return

            if len(products) == 1:
                product = products[0]
            else:
                product = self._choose_product(products)
                if product is None:
                    return

        # Check if already in list — increment qty
        for item in self.label_items:
            if item["product"].id == product.id:
                item["quantity"] += 1
                self._refresh_table()
                self.search_input.clear()
                self.search_input.setFocus()
                return

        self.label_items.append({"product": product, "quantity": 1})
        self._refresh_table()
        self.search_input.clear()
        self.search_input.setFocus()

    def _choose_product(self, products) -> object:
        """Show a selection dialog when multiple products match."""
        from PyQt6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QTableWidget,
            QTableWidgetItem,
            QHeaderView,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Select Product")
        dlg.setMinimumSize(500, 300)
        layout = QVBoxLayout(dlg)

        tbl = QTableWidget()
        tbl.setColumnCount(3)
        tbl.setHorizontalHeaderLabels(["Name", "Barcode", "Price"])
        tbl.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for p in products:
            row = tbl.rowCount()
            tbl.insertRow(row)
            tbl.setItem(row, 0, QTableWidgetItem(p.name_en))
            tbl.setItem(row, 1, QTableWidgetItem(p.barcode))
            tbl.setItem(row, 2, QTableWidgetItem(format_currency(p.price)))

        tbl.doubleClicked.connect(dlg.accept)
        layout.addWidget(tbl)

        btn_layout = QHBoxLayout()
        btn_select = QPushButton("Select")
        btn_select.setProperty("class", "primary")
        btn_select.clicked.connect(dlg.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dlg.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_select)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        if dlg.exec() and tbl.currentRow() >= 0:
            return products[tbl.currentRow()]
        return None

    def _refresh_table(self) -> None:
        """Rebuild the table from label_items."""
        self.table.setRowCount(0)
        total_labels = 0

        for i, item in enumerate(self.label_items):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, TABLE_ROW_HEIGHT)

            self.table.setItem(
                row, 0, QTableWidgetItem(item["product"].name_en)
            )
            self.table.setItem(
                row, 1, QTableWidgetItem(item["product"].barcode)
            )
            self.table.setItem(
                row, 2, QTableWidgetItem(format_currency(item["product"].price))
            )

            # Qty input (simple text field with proper height)
            qty_input = QLineEdit()
            qty_input.setObjectName("LabelQtyInput")
            qty_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qty_input.setValidator(QIntValidator(1, 999))
            qty_input.setText(str(item["quantity"]))
            qty_input.textChanged.connect(
                lambda text, idx=i: self._update_qty(idx, text)
            )
            self.table.setCellWidget(row, 3, qty_input)

            total_labels += item["quantity"]

        self.lbl_total.setText(f"Total labels: {total_labels}")

    def _update_qty(self, index: int, text: str) -> None:
        """Update quantity for item at index."""
        if 0 <= index < len(self.label_items):
            try:
                value = int(text) if text else 1
            except ValueError:
                value = 1
            self.label_items[index]["quantity"] = max(1, value)
            total = sum(item["quantity"] for item in self.label_items)
            self.lbl_total.setText(f"Total labels: {total}")

    def _remove_selected(self) -> None:
        """Remove selected product from label queue."""
        row = self.table.currentRow()
        if 0 <= row < len(self.label_items):
            del self.label_items[row]
            self._refresh_table()

    def _clear_all(self) -> None:
        """Clear all items from label queue."""
        self.label_items.clear()
        self._refresh_table()

    def _preview_label(self) -> None:
        """Show a visual preview of a label for the selected product."""
        if not self.label_items:
            QMessageBox.warning(
                self, "No Items", "Add a product first to preview its label."
            )
            return

        row = self.table.currentRow()
        if row < 0:
            row = 0

        product = self.label_items[row]["product"]

        from cbpos.ui.dialogs.label_preview_dialog import LabelPreviewDialog

        dlg = LabelPreviewDialog(product, parent=self)
        dlg.exec()

    def _print_labels(self) -> None:
        """Generate and send label print commands."""
        if not self.label_items:
            QMessageBox.warning(
                self, "Empty", "No products to print labels for."
            )
            return

        try:
            commands = LabelService.generate_batch_commands(self.label_items)
            worker = PrintWorker()
            worker.add_job("print_commands", commands)

            total = sum(item["quantity"] for item in self.label_items)
            QMessageBox.information(
                self, "Printing", f"Sending {total} labels to printer..."
            )
        except Exception as e:
            logger.error(f"Label printing failed: {e}")
            QMessageBox.critical(self, "Error", f"Print failed: {e}")
