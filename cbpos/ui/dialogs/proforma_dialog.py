import logging
from decimal import Decimal

from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtGui import QColor, QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.proforma_service import ProformaService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class ProformaDialog(QDialog):
    """Dialog for creating a new Proforma / Quotation."""

    def __init__(self, parent=None) -> None:
        """Build the dialog and load products/customers for a fresh proforma."""
        super().__init__(parent)
        self.setWindowTitle(_t("proforma.title"))
        self.setMinimumSize(700, 550)
        self.items: list[dict] = []
        self.products_cache: dict = {}
        self.init_ui()
        self.refresh_table()
        self.load_products()
        self.load_customers()

    def init_ui(self) -> None:
        """Build the header form, product search, items grid, and footer controls."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header Section
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        # Searchable -- type to filter (#294), same recipe already proven
        # for payment_dialog.py's customer combo. setEditable(True) alone
        # (the prior state here) makes it look searchable without actually
        # filtering anything -- worse than a plain combo, since it invites
        # typing that then does nothing. The QCompleter itself is built in
        # load_customers() where the current customer list is available.
        self.customer_combo = QComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.customer_combo.addItem(_t("proforma.no_customer"), None)
        form.addRow(_t("proforma.customer"), self.customer_combo)

        # QLineEdit + QIntValidator instead of QSpinBox for clean rendering
        # (QSpinBox +/- buttons break under QSS), matching the pattern
        # already proven in product_editor.py's Stock group.
        self.validity_spin = QLineEdit()
        self.validity_spin.setValidator(QIntValidator(1, 365))
        self.validity_spin.setText("30")
        form.addRow(_t("proforma.validity"), self.validity_spin)

        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.setPlaceholderText(_t("proforma.notes_placeholder"))
        form.addRow(_t("common.notes") + ":", self.notes_edit)

        layout.addLayout(form)

        # Product Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel(_t("proforma.add_product")))
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText(_t("proforma.search_placeholder"))
        self.product_completer = QCompleter()
        self.product_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.product_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.product_search.setCompleter(self.product_completer)
        self.product_search.returnPressed.connect(self.add_product)
        search_layout.addWidget(self.product_search, 1)

        add_btn = QPushButton(_t("common.add"))
        add_btn.setAutoDefault(False)  # Enter in the search already adds; don't fire twice (#546)
        add_btn.clicked.connect(self.add_product)
        search_layout.addWidget(add_btn)

        layout.addLayout(search_layout)

        # Items Grid
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(6)
        self.items_table.setHorizontalHeaderLabels(
            [
                _t("proforma.col_product"),
                _t("proforma.col_qty"),
                _t("proforma.col_unit_price"),
                _t("proforma.col_disc_type"),
                _t("proforma.col_disc_value"),
                _t("common.total"),
            ]
        )
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items_table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.items_table)

        # Footer: Total + Create
        footer = QHBoxLayout()

        self.total_label = QLabel(f"<b>{_t('common.total')}: {format_currency(0)}</b>")
        self.total_label.setStyleSheet("font-size: 16px;")
        footer.addWidget(self.total_label)

        footer.addStretch()

        cancel_btn = QPushButton(_t("common.cancel"))
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        create_btn = QPushButton(_t("proforma.btn_create"))
        create_btn.setStyleSheet("background-color: #00BCEB; color: white; font-weight: bold; padding: 8px 20px;")
        create_btn.setAutoDefault(False)
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

        self.customer_combo.lineEdit().setPlaceholderText(_t("proforma.search_customer_placeholder"))
        names = [_t("proforma.no_customer")] + [c.name for c in customers]
        completer = QCompleter(names, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.customer_combo.setCompleter(completer)

    def add_product(self) -> None:
        """Add selected product to items grid."""
        text = self.product_search.text().strip()
        if not text:
            return

        product = self.products_cache.get(text)
        if not product:
            # Try barcode lookup
            for _key, p in self.products_cache.items():
                if hasattr(p, "barcode") and p.barcode == text:
                    product = p
                    break

        if not product:
            QMessageBox.warning(self, _t("proforma.not_found"), _t("proforma.product_not_found", name=text))
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

        if not self.items:
            self.items_table.insertRow(0)
            empty_item = QTableWidgetItem(_t("proforma.items_empty_state"))
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(QColor("gray"))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.items_table.setItem(0, 0, empty_item)
            self.items_table.setSpan(0, 0, 1, self.items_table.columnCount())
            self.total_label.setText(f"<b>{_t('common.total')}: {format_currency(total)}</b>")
            return

        for row, item in enumerate(self.items):
            self.items_table.insertRow(row)

            self.items_table.setItem(row, 0, QTableWidgetItem(item["product_name"]))

            qty_item = QTableWidgetItem(f"{item['quantity']:.3f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, 1, qty_item)

            price_item = QTableWidgetItem(f"{item['unit_price']:.2f}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, 2, price_item)

            self.items_table.setItem(row, 3, QTableWidgetItem(item["discount_type"]))

            disc_item = QTableWidgetItem(f"{item['discount_value']:.2f}")
            disc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, 4, disc_item)

            line_total = item["line_total"]
            total_item = QTableWidgetItem(format_currency(line_total))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, 5, total_item)

            total += line_total

        self.total_label.setText(f"<b>{_t('common.total')}: {format_currency(total)}</b>")

    def show_context_menu(self, position) -> None:
        """Show context menu for editing/removing items."""
        if self.items_table.rowCount() == 0:
            return

        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        edit_qty = menu.addAction(_t("proforma.change_qty"))
        remove = menu.addAction(_t("common.remove"))

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
        qty, ok = QInputDialog.getDouble(
            self, _t("proforma.change_qty"), _t("proforma.new_qty"), current, 0.001, 99999.0, 3
        )
        if ok:
            self.items[row]["quantity"] = Decimal(str(qty))
            self.items[row]["line_total"] = self.items[row]["quantity"] * self.items[row]["unit_price"]
            self.refresh_table()

    def create_proforma(self) -> None:
        """Create the proforma via ProformaService."""
        if not self.items:
            QMessageBox.warning(self, _t("proforma.no_items"), _t("proforma.no_items_msg"))
            return

        customer_id = self.customer_combo.currentData()
        validity = int(self.validity_spin.text() or 30)
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
                _t("common.success"),
                _t("proforma.create_success", doc_number=proforma.document_number),
            )
            self.accept()
        else:
            QMessageBox.critical(self, _t("common.error"), _t("proforma.create_failed"))
