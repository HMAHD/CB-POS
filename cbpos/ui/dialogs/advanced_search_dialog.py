"""
Advanced Product Search Dialog ([F3]).
Supports filters: Category, Supplier, Price Range.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QDoubleSpinBox,
    QHeaderView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence, QBrush, QColor
from decimal import Decimal
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.utils.formatters import format_currency, get_currency_symbol
from cbpos.i18n import _t


class AdvancedSearchDialog(QDialog):
    """
    Advanced Product Search Dialog (F3).
    Supports filters: Category, Supplier, Price Range.
    """

    product_selected = pyqtSignal(object)  # Emits selected Product

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("advanced_search.title"))
        self.setMinimumSize(950, 620)
        self.setObjectName("AdvancedSearchDialog")
        self.product_service = ProductService()
        self.init_ui()
        self.load_filters()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        self.title_label = QLabel("")
        self.title_label.setObjectName("AdvSearchTitle")
        layout.addWidget(self.title_label)

        # Filters Row 1: Search + Category + Supplier
        filter_row1 = QHBoxLayout()
        filter_row1.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("")
        self.search_input.textChanged.connect(self.perform_search)
        filter_row1.addWidget(self.search_input, stretch=2)

        self.category_combo = QComboBox()
        self.category_combo.setObjectName("SearchCategoryCombo")
        self.category_combo.addItem(_t("advanced_search.all_categories"), None)
        self.category_combo.currentIndexChanged.connect(self.perform_search)
        filter_row1.addWidget(self.category_combo, stretch=1)

        self.supplier_combo = QComboBox()
        self.supplier_combo.setObjectName("SearchSupplierCombo")
        self.supplier_combo.addItem(_t("advanced_search.all_suppliers"), None)
        self.supplier_combo.currentIndexChanged.connect(self.perform_search)
        filter_row1.addWidget(self.supplier_combo, stretch=1)

        layout.addLayout(filter_row1)

        # Filters Row 2: Price Range
        filter_row2 = QHBoxLayout()
        filter_row2.setSpacing(10)

        self.lbl_price = QLabel("")
        self.lbl_price.setObjectName("SearchFilterLabel")
        filter_row2.addWidget(self.lbl_price)

        self.price_min = QDoubleSpinBox()
        self.price_min.setObjectName("SearchPriceMin")
        self.price_min.setRange(0, 999999)
        self.price_min.setPrefix(f"{get_currency_symbol()} ")
        self.price_min.valueChanged.connect(self.perform_search)
        filter_row2.addWidget(self.price_min)

        self.lbl_to = QLabel("")
        self.lbl_to.setObjectName("SearchFilterLabel")
        filter_row2.addWidget(self.lbl_to)

        self.price_max = QDoubleSpinBox()
        self.price_max.setObjectName("SearchPriceMax")
        self.price_max.setRange(0, 999999)
        self.price_max.setValue(999999)
        self.price_max.setPrefix(f"{get_currency_symbol()} ")
        self.price_max.valueChanged.connect(self.perform_search)
        filter_row2.addWidget(self.price_max)

        filter_row2.addStretch()
        layout.addLayout(filter_row2)

        # Results Table
        self.table = QTableWidget()
        self.table.setObjectName("SearchResultsTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["", "", "", "", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.on_select)
        layout.addWidget(self.table)

        # Bottom Bar: Result count + Buttons
        btn_layout = QHBoxLayout()

        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("SearchResultCount")
        btn_layout.addWidget(self.lbl_count)

        btn_layout.addStretch()

        self.btn_select = QPushButton("")
        self.btn_select.setObjectName("BtnSearchSelect")
        self.btn_select.clicked.connect(self.on_select)
        btn_layout.addWidget(self.btn_select)

        self.btn_cancel = QPushButton("")
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(self.on_select)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.reject)

        # Focus
        self.search_input.setFocus()

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("advanced_search.title"))
        self.title_label.setText(_t("advanced_search.title_alt"))
        self.search_input.setPlaceholderText(_t("advanced_search.search_placeholder"))
        self.lbl_price.setText(_t("advanced_search.price_label"))
        self.lbl_to.setText(_t("advanced_search.price_to"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("advanced_search.header_name"),
                _t("advanced_search.header_barcode"),
                _t("advanced_search.header_stock"),
                _t("advanced_search.header_price"),
                _t("advanced_search.header_category"),
            ]
        )
        self.lbl_count.setText(_t("advanced_search.result_count", count=0))
        self.btn_select.setText(_t("advanced_search.btn_select"))
        self.btn_cancel.setText(_t("advanced_search.btn_cancel"))

    def load_filters(self):
        """Load categories and suppliers for filters."""
        categories = CategoryService.get_all()
        for cat in categories:
            self.category_combo.addItem(cat.name, cat.id)

        suppliers = SupplierService.get_all_suppliers()
        for sup in suppliers:
            self.supplier_combo.addItem(sup.company_name, sup.id)

    def _get_text_color(self) -> QColor:
        """Get theme-aware text color."""
        from cbpos.core.services.theme_service import ThemeService

        is_dark = ThemeService.current_theme.lower() == "dark"
        return QColor("#FFFFFF") if is_dark else QColor("#212529")

    def perform_search(self):
        """Execute search with filters."""
        query = self.search_input.text()
        category_id = self.category_combo.currentData()
        supplier_id = self.supplier_combo.currentData()
        min_price = Decimal(str(self.price_min.value()))
        max_price = Decimal(str(self.price_max.value()))

        # Get products
        products = self.product_service.search_products(query, mode="ALL")

        # Apply filters
        filtered = []
        for p in products:
            if category_id and p.category_id != category_id:
                continue
            if supplier_id and p.default_supplier_id != supplier_id:
                continue
            if not (min_price <= p.price <= max_price):
                continue
            filtered.append(p)

        # Theme-aware text brush
        text_brush = QBrush(self._get_text_color())

        # Populate table
        self.table.setRowCount(len(filtered))
        for row, product in enumerate(filtered):
            name_item = QTableWidgetItem(product.name_en)
            name_item.setForeground(text_brush)
            self.table.setItem(row, 0, name_item)

            barcode_item = QTableWidgetItem(product.barcode)
            barcode_item.setForeground(text_brush)
            self.table.setItem(row, 1, barcode_item)

            stock_item = QTableWidgetItem(f"{float(product.stock_qty):.2f}")  # noqa: E231
            stock_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            stock_item.setForeground(text_brush)
            self.table.setItem(row, 2, stock_item)

            price_item = QTableWidgetItem(format_currency(product.price))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            price_item.setForeground(text_brush)
            self.table.setItem(row, 3, price_item)

            cat_name = product.category.name if product.category else "-"
            cat_item = QTableWidgetItem(cat_name)
            cat_item.setForeground(text_brush)
            self.table.setItem(row, 4, cat_item)

            # Store product object
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, product)

        # Update result count
        self.lbl_count.setText(_t("advanced_search.result_count", count=len(filtered)))

    def on_select(self):
        """Emit selected product and close dialog."""
        row = self.table.currentRow()
        if row >= 0:
            product = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.product_selected.emit(product)
            self.accept()
