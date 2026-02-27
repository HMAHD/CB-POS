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
    QSpinBox,
    QMessageBox,
)
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.label_service import LabelService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)


class LabelPrintDialog(QDialog):
    """Dialog to search products, set quantities, and print barcode labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Print Barcode Labels")
        self.setMinimumSize(700, 500)
        self.setObjectName("LabelPrintDialog")
        self.product_service = ProductService()
        self.label_items = []  # List of {'product': Product, 'quantity': int}
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search product by name or barcode...")
        self.search_input.returnPressed.connect(self._add_product)
        search_layout.addWidget(self.search_input, 1)

        btn_add = QPushButton("Add")
        btn_add.setProperty("class", "primary")
        btn_add.clicked.connect(self._add_product)
        search_layout.addWidget(btn_add)

        layout.addLayout(search_layout)

        # Label queue table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Product", "Barcode", "Price", "Qty"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 80)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Summary + actions
        btn_layout = QHBoxLayout()

        self.lbl_total = QLabel("Total labels: 0")
        self.lbl_total.setStyleSheet("font-weight: bold; background: transparent;")
        btn_layout.addWidget(self.lbl_total)

        btn_layout.addStretch()

        btn_remove = QPushButton("Remove Selected")
        btn_remove.clicked.connect(self._remove_selected)
        btn_layout.addWidget(btn_remove)

        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self._clear_all)
        btn_layout.addWidget(btn_clear)

        btn_print = QPushButton("Print Labels")
        btn_print.setProperty("class", "primary")
        btn_print.clicked.connect(self._print_labels)
        btn_layout.addWidget(btn_print)

        layout.addLayout(btn_layout)

    def _add_product(self) -> None:
        """Search for product and add to label queue."""
        query = self.search_input.text().strip()
        if not query:
            return

        products = self.product_service.search_products(query, mode="ALL")

        if not products:
            QMessageBox.warning(self, "Not Found", f"No product found for '{query}'.")
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
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView

        dlg = QDialog(self)
        dlg.setWindowTitle("Select Product")
        dlg.setMinimumSize(500, 300)
        layout = QVBoxLayout(dlg)

        tbl = QTableWidget()
        tbl.setColumnCount(3)
        tbl.setHorizontalHeaderLabels(["Name", "Barcode", "Price"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
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

            self.table.setItem(row, 0, QTableWidgetItem(item["product"].name_en))
            self.table.setItem(row, 1, QTableWidgetItem(item["product"].barcode))
            self.table.setItem(row, 2, QTableWidgetItem(format_currency(item["product"].price)))

            # Qty spin box
            spin = QSpinBox()
            spin.setMinimum(1)
            spin.setMaximum(999)
            spin.setValue(item["quantity"])
            spin.valueChanged.connect(lambda val, idx=i: self._update_qty(idx, val))
            self.table.setCellWidget(row, 3, spin)

            total_labels += item["quantity"]

        self.lbl_total.setText(f"Total labels: {total_labels}")

    def _update_qty(self, index: int, value: int) -> None:
        """Update quantity for item at index."""
        if 0 <= index < len(self.label_items):
            self.label_items[index]["quantity"] = value
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

    def _print_labels(self) -> None:
        """Generate and send label print commands."""
        if not self.label_items:
            QMessageBox.warning(self, "Empty", "No products to print labels for.")
            return

        try:
            commands = LabelService.generate_batch_commands(self.label_items)
            worker = PrintWorker()
            worker.add_job("print_commands", commands)

            total = sum(item["quantity"] for item in self.label_items)
            QMessageBox.information(self, "Printing", f"Sending {total} labels to printer...")
        except Exception as e:
            logger.error(f"Label printing failed: {e}")
            QMessageBox.critical(self, "Error", f"Print failed: {e}")
