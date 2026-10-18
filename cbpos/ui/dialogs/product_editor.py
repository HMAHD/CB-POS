from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QDoubleValidator, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.config import Config
from cbpos.core.models import Product
from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import get_currency_symbol
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


def _color_icon(hex_color: str, size: int = 12) -> QIcon:
    """Create a small colored square icon for category display."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(hex_color or "#FFFFFF"))
    return QIcon(pixmap)


class ProductEditor(QDialog):
    """Tabbed dialog for creating or editing a product: general info, inventory, bundle composition, and image."""

    def __init__(self, product: Product = None, parent=None):
        """Initialize the dialog, pre-filling fields when editing an existing product."""
        super().__init__(parent)
        self.product = product
        self.inventory_service = InventoryService()
        self.setWindowTitle(_t("product_editor.title_edit") if product else _t("product_editor.title_add"))
        self.setMinimumWidth(700)
        self.setMinimumHeight(520)
        self.resize(750, 580)

        self.current_image_path: str | None = None
        self.categories = []
        self.suppliers = []
        self.load_categories()
        self.load_suppliers()

        self.setup_ui()
        if product:
            self.load_data()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def load_categories(self):
        """Load top-level categories (with subcategories) for the category combo."""
        self.categories = CategoryService.get_top_level_with_subcategories()

    def load_suppliers(self):
        """Load all suppliers, including inactive ones, for the default supplier combo."""
        self.suppliers = SupplierService.get_all_suppliers(active_only=False)

    def setup_ui(self):
        """Build the General, Inventory, Composition, and Image tabs plus save/cancel buttons."""
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # Tab 1: General
        self.tab_general = QWidget()
        self.setup_general_tab()
        self.tabs.addTab(self.tab_general, _t("product_editor.tab_general"))

        # Tab 2: Inventory
        self.tab_inventory = QWidget()
        self.setup_inventory_tab()
        self.tabs.addTab(self.tab_inventory, _t("product_editor.tab_inventory"))

        # Tab 3: Composition
        self.tab_composition = QWidget()
        self.setup_composition_tab()
        self.tabs.addTab(self.tab_composition, _t("product_editor.tab_composition"))

        # Tab 4: Image
        self.tab_image = QWidget()
        self.setup_image_tab()
        self.tabs.addTab(self.tab_image, _t("product_editor.tab_image"))

        layout.addWidget(self.tabs)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.save_product,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

    def setup_general_tab(self):
        """Build the General tab: names (EN/SI/TA), barcode, category, selling price, and cost price."""
        layout = QFormLayout(self.tab_general)
        layout.setVerticalSpacing(12)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name_en_input = QLineEdit()
        self.name_en_input.setPlaceholderText(_t("product_editor.name_en_placeholder"))
        self.name_si_input = QLineEdit()
        self.name_si_input.setPlaceholderText(_t("product_editor.name_si_placeholder"))
        self.name_ta_input = QLineEdit()
        self.name_ta_input.setPlaceholderText(_t("product_editor.name_ta_placeholder"))

        self.barcode_input = QLineEdit()
        # Settings -> System -> Auto-Generate Barcodes lets a new product be saved without one (#641)
        self._auto_barcode = bool(ConfigService.get("auto_generate_barcodes"))
        placeholder_key = "barcode_placeholder_auto" if self._auto_barcode else "barcode_placeholder"
        self.barcode_input.setPlaceholderText(_t(f"product_editor.{placeholder_key}"))

        self.category_combo = QComboBox()
        self.category_combo.addItem(_t("product_editor.select_category"), None)
        for cat in self.categories:
            self.category_combo.addItem(_color_icon(cat.color), cat.name, cat.id)
            for sub in sorted(cat.subcategories, key=lambda c: c.name):
                self.category_combo.addItem(_color_icon(sub.color), f"    {sub.name}", sub.id)

        # QLineEdit + validator instead of QDoubleSpinBox -- native +/-
        # steppers break under QSS (see the Stock group below).
        self.price_input = QLineEdit()
        self.price_input.setPlaceholderText(f"{get_currency_symbol()} 0.00")
        self.price_input.setValidator(QDoubleValidator(0.0, 1000000.0, 2, self))

        self.cost_input = QLineEdit()
        self.cost_input.setPlaceholderText(f"{get_currency_symbol()} 0.00")
        self.cost_input.setValidator(QDoubleValidator(0.0, 1000000.0, 2, self))

        layout.addRow(_t("product_editor.name_en"), self.name_en_input)
        layout.addRow(_t("product_editor.name_si"), self.name_si_input)
        layout.addRow(_t("product_editor.name_ta"), self.name_ta_input)
        layout.addRow(_t("product_editor.barcode"), self.barcode_input)
        layout.addRow(_t("product_editor.category"), self.category_combo)
        layout.addRow(_t("product_editor.selling_price"), self.price_input)
        layout.addRow(_t("product_editor.cost_price"), self.cost_input)

    def setup_inventory_tab(self):
        """Build the Inventory tab: stock levels, supplier/unit selection, and weighted/service item toggles."""
        tab_layout = QVBoxLayout(self.tab_inventory)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        self.inventory_scroll = QScrollArea()
        self.inventory_scroll.setObjectName("InventoryScrollArea")
        self.inventory_scroll.setWidgetResizable(True)
        self.inventory_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inventory_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setObjectName("InventoryScrollInner")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Stock group — 3-column row to save vertical height and prevent vertical compression
        grp_stock = QGroupBox(_t("product_editor.group_stock"))
        stock_layout = QHBoxLayout(grp_stock)
        stock_layout.setContentsMargins(12, 12, 12, 12)
        stock_layout.setSpacing(12)

        stock_validator = QDoubleValidator(-10000.0, 1000000.0, 3)
        reorder_validator = QDoubleValidator(0.0, 10000.0, 3)

        self.stock_input = QLineEdit()
        self.stock_input.setPlaceholderText("0.000")
        self.stock_input.setValidator(stock_validator)
        self.stock_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.reorder_input = QLineEdit()
        self.reorder_input.setPlaceholderText("0.000")
        self.reorder_input.setValidator(reorder_validator)
        self.reorder_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.preferred_qty_input = QLineEdit()
        self.preferred_qty_input.setPlaceholderText("0.000")
        self.preferred_qty_input.setValidator(reorder_validator)
        self.preferred_qty_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Column 1: Stock Qty
        col_stock = QVBoxLayout()
        col_stock.setSpacing(4)
        lbl_stock = QLabel(_t("product_editor.stock_qty"))
        lbl_stock.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        col_stock.addWidget(lbl_stock)
        col_stock.addWidget(self.stock_input)
        stock_layout.addLayout(col_stock, 1)

        # Column 2: Reorder Point
        col_reorder = QVBoxLayout()
        col_reorder.setSpacing(4)
        lbl_reorder = QLabel(_t("product_editor.reorder_point"))
        lbl_reorder.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        col_reorder.addWidget(lbl_reorder)
        col_reorder.addWidget(self.reorder_input)
        stock_layout.addLayout(col_reorder, 1)

        # Column 3: Preferred Qty
        col_preferred = QVBoxLayout()
        col_preferred.setSpacing(4)
        lbl_preferred = QLabel(_t("product_editor.preferred_qty"))
        lbl_preferred.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        col_preferred.addWidget(lbl_preferred)
        col_preferred.addWidget(self.preferred_qty_input)
        stock_layout.addLayout(col_preferred, 1)

        layout.addWidget(grp_stock)

        # Supplier + Unit row — side by side to save vertical space
        sup_unit_layout = QHBoxLayout()
        sup_unit_layout.setSpacing(10)

        grp_supplier = QGroupBox(_t("product_editor.group_supplier"))
        supplier_layout = QVBoxLayout(grp_supplier)
        supplier_layout.setContentsMargins(12, 12, 12, 12)
        self.supplier_combo = QComboBox()
        self.supplier_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.supplier_combo.addItem(_t("product_editor.no_default_supplier"), None)
        for supplier in self.suppliers:
            self.supplier_combo.addItem(supplier.company_name, supplier.id)
        supplier_layout.addWidget(self.supplier_combo)
        sup_unit_layout.addWidget(grp_supplier)

        grp_unit = QGroupBox(_t("product_editor.group_uom"))
        unit_inner = QVBoxLayout(grp_unit)
        unit_inner.setContentsMargins(12, 12, 12, 12)
        self.unit_combo = QComboBox()
        self.unit_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.unit_combo.addItem(_t("product_editor.no_unit"), None)
        from cbpos.core.services.unit_service import UnitService

        for unit in UnitService.get_all():
            self.unit_combo.addItem(f"{unit.name} ({unit.abbreviation})", unit.id)
        unit_inner.addWidget(self.unit_combo)
        sup_unit_layout.addWidget(grp_unit)

        layout.addLayout(sup_unit_layout)

        # Item type group — checkbox + inline hint on same row
        grp_type = QGroupBox(_t("product_editor.group_item_type"))
        type_layout = QVBoxLayout(grp_type)
        type_layout.setContentsMargins(12, 12, 12, 12)
        type_layout.setSpacing(8)

        # 1. Weighted
        row_weighted = QHBoxLayout()
        row_weighted.setSpacing(8)
        self.weighted_check = QCheckBox(_t("product_editor.weighted_item"))
        self.weighted_check.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        row_weighted.addWidget(self.weighted_check)
        self.weighted_hint = QLabel(_t("product_editor.weighted_hint"))
        self.weighted_hint.setObjectName("ToggleHint")
        self.weighted_hint.setWordWrap(True)
        self.weighted_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row_weighted.addWidget(self.weighted_hint, 1)
        type_layout.addLayout(row_weighted)

        # 2. Service
        row_service = QHBoxLayout()
        row_service.setSpacing(8)
        self.service_check = QCheckBox(_t("product_editor.service_item"))
        self.service_check.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        row_service.addWidget(self.service_check)
        self.service_hint = QLabel(_t("product_editor.service_hint"))
        self.service_hint.setObjectName("ToggleHint")
        self.service_hint.setWordWrap(True)
        self.service_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row_service.addWidget(self.service_hint, 1)
        type_layout.addLayout(row_service)

        # 3. Price change
        row_price_change = QHBoxLayout()
        row_price_change.setSpacing(8)
        self.price_change_allowed_check = QCheckBox(_t("product_editor.price_change_allowed"))
        self.price_change_allowed_check.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        self.price_change_allowed_check.setChecked(True)
        row_price_change.addWidget(self.price_change_allowed_check)
        self.price_change_hint = QLabel(_t("product_editor.price_change_hint"))
        self.price_change_hint.setObjectName("ToggleHint")
        self.price_change_hint.setWordWrap(True)
        self.price_change_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row_price_change.addWidget(self.price_change_hint, 1)
        type_layout.addLayout(row_price_change)

        # 4. Age restricted
        row_age_restricted = QHBoxLayout()
        row_age_restricted.setSpacing(8)
        self.age_restricted_check = QCheckBox(_t("product_editor.age_restricted"))
        self.age_restricted_check.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        row_age_restricted.addWidget(self.age_restricted_check)
        self.age_restricted_hint = QLabel(_t("product_editor.age_restricted_hint"))
        self.age_restricted_hint.setObjectName("ToggleHint")
        self.age_restricted_hint.setWordWrap(True)
        self.age_restricted_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row_age_restricted.addWidget(self.age_restricted_hint, 1)
        type_layout.addLayout(row_age_restricted)

        layout.addWidget(grp_type)
        layout.addStretch(1)

        self.inventory_scroll.setWidget(scroll_content)
        tab_layout.addWidget(self.inventory_scroll)

    def setup_composition_tab(self):
        """Build the Composition tab: add-by-barcode row and the table of bundled component products."""
        layout = QVBoxLayout(self.tab_composition)

        # Add component area
        add_layout = QHBoxLayout()
        self.comp_barcode_input = QLineEdit()
        self.comp_barcode_input.setPlaceholderText(_t("product_editor.composition_barcode_placeholder"))
        self.comp_qty_input = QLineEdit("1.00")
        self.comp_qty_input.setValidator(QDoubleValidator(0.001, 1000.0, 2, self))
        self.btn_add_component = QPushButton(_t("product_editor.btn_add_component"))
        self.btn_add_component.clicked.connect(self.add_component)
        self.comp_barcode_input.returnPressed.connect(self.add_component)

        add_layout.addWidget(self.comp_barcode_input)
        add_layout.addWidget(self.comp_qty_input)
        add_layout.addWidget(self.btn_add_component)
        layout.addLayout(add_layout)

        # Table
        self.comp_table = QTableWidget()
        self.comp_table.setColumnCount(4)
        self.comp_table.setHorizontalHeaderLabels(
            [
                _t("common.id"),
                _t("common.name"),
                _t("product_editor.comp_header_qty"),
                _t("product_editor.comp_header_action"),
            ]
        )
        self.comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.comp_table.setAlternatingRowColors(True)
        self.comp_table.hideColumn(0)  # Hide ID
        layout.addWidget(self.comp_table)

    def add_component(self):
        """Look up the product by the entered barcode and add it as a bundle component row."""
        barcode = self.comp_barcode_input.text().strip()
        qty = self._parse_decimal(self.comp_qty_input.text(), fallback="1")

        if not barcode:
            return

        product = self.inventory_service.get_product_by_barcode(barcode)
        if not product:
            QMessageBox.warning(
                self, _t("product_editor.not_found_title"), _t("product_editor.not_found_barcode", barcode=barcode)
            )
            self.comp_barcode_input.setFocus()
            return

        if self.product and product.id == self.product.id:
            QMessageBox.warning(self, _t("product_editor.invalid_title"), _t("product_editor.cannot_add_self"))
            return

        # Check if already exists in table
        for row in range(self.comp_table.rowCount()):
            if self.comp_table.item(row, 0).text() == str(product.id):
                QMessageBox.warning(
                    self, _t("product_editor.duplicate_title"), _t("product_editor.already_added", name=product.name_en)
                )
                return

        row = self.comp_table.rowCount()
        self.comp_table.insertRow(row)
        self.comp_table.setItem(row, 0, QTableWidgetItem(str(product.id)))
        self.comp_table.setItem(row, 1, QTableWidgetItem(product.name_en))
        self.comp_table.setItem(row, 2, QTableWidgetItem(str(qty)))

        remove_btn = QPushButton(_t("product_editor.btn_remove_component"))
        target_row = row
        remove_btn.clicked.connect(lambda checked, r=target_row: self._remove_component(r))
        self.comp_table.setCellWidget(row, 3, remove_btn)

        self.comp_barcode_input.clear()
        self.comp_barcode_input.setFocus()

    def _remove_component(self, row: int) -> None:
        """Remove a component row. Re-wire buttons after removal."""
        if row < self.comp_table.rowCount():
            self.comp_table.removeRow(row)
            # Re-wire remove buttons with correct row indices
            for r in range(self.comp_table.rowCount()):
                btn = self.comp_table.cellWidget(r, 3)
                if btn:
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda checked, idx=r: self._remove_component(idx))

    def setup_image_tab(self):
        """Build the Image tab: preview label and upload/clear buttons."""
        layout = QVBoxLayout(self.tab_image)

        # Center everything vertically and horizontally
        layout.addStretch()

        self.lbl_image = QLabel(_t("product_editor.no_image"))
        self.lbl_image.setObjectName("ProductImagePreview")
        self.lbl_image.setFixedSize(200, 200)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setScaledContents(True)
        layout.addWidget(self.lbl_image, 0, Qt.AlignmentFlag.AlignCenter)

        # Buttons row — centered
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_upload = QPushButton(_t("product_editor.btn_upload_image"))
        self.btn_upload.clicked.connect(self.upload_image)
        btn_row.addWidget(self.btn_upload)

        self.btn_clear_img = QPushButton(_t("product_editor.btn_clear_image"))
        self.btn_clear_img.clicked.connect(self.clear_image)
        btn_row.addWidget(self.btn_clear_img)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

        self.current_image_path = None

    def upload_image(self):
        """Let the user pick an image file, copy it into the product images folder, and show it."""
        import os
        import shutil

        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, _t("product_editor.select_image_title"), "", "Images (*.png *.jpg *.jpeg)"
        )

        if file_path:
            # Copy to assets
            filename = os.path.basename(file_path)
            target_dir = str(Config.DATA_DIR / "product_images")
            os.makedirs(target_dir, exist_ok=True)

            target_path = os.path.join(target_dir, filename)
            shutil.copy(file_path, target_path)

            self.current_image_path = f"product_images/{filename}"
            self.show_image(target_path)

    def clear_image(self):
        """Clear the selected product image."""
        self.current_image_path = None
        self.lbl_image.clear()
        self.lbl_image.setText(_t("product_editor.no_image"))

    def show_image(self, path):
        """Display the image at the given path in the preview label, or a not-found message."""
        import os

        from PyQt6.QtGui import QPixmap

        if os.path.exists(path):
            pixmap = QPixmap(path)
            self.lbl_image.setPixmap(pixmap)
        else:
            self.lbl_image.setText(_t("product_editor.image_not_found"))

    def load_data(self):
        """Populate all tabs' fields, including bundle components, from the product being edited."""
        self.barcode_input.setText(self.product.barcode)
        self.barcode_input.setReadOnly(True)
        self.name_en_input.setText(self.product.name_en)
        self.name_si_input.setText(self.product.name_si or "")
        self.name_ta_input.setText(self.product.name_ta or "")

        index = self.category_combo.findData(self.product.category_id)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)

        self.price_input.setText(format(Decimal(self.product.price).quantize(Decimal("0.01")), "f"))
        self.cost_input.setText(format(Decimal(self.product.cost).quantize(Decimal("0.01")), "f"))

        _q = Decimal("0.001")
        self.stock_input.setText(
            "" if self.product.stock_qty is None else format(self.product.stock_qty.quantize(_q), "f")
        )
        self.reorder_input.setText(
            "" if self.product.reorder_point is None else format(self.product.reorder_point.quantize(_q), "f")
        )
        self.preferred_qty_input.setText(
            "" if self.product.preferred_qty is None else format(self.product.preferred_qty.quantize(_q), "f")
        )
        self.weighted_check.setChecked(self.product.is_weighted)
        self.service_check.setChecked(self.product.is_service)
        self.price_change_allowed_check.setChecked(self.product.price_change_allowed)
        self.age_restricted_check.setChecked(self.product.is_age_restricted)

        # Load unit
        if self.product.unit_id:
            idx = self.unit_combo.findData(self.product.unit_id)
            if idx >= 0:
                self.unit_combo.setCurrentIndex(idx)

        # Load supplier
        if hasattr(self.product, "default_supplier_id") and self.product.default_supplier_id:
            idx = self.supplier_combo.findData(self.product.default_supplier_id)
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)

        if self.product.image_path:
            full_path = str(Config.DATA_DIR / self.product.image_path)
            self.show_image(full_path)
            self.current_image_path = self.product.image_path

        # Load components
        components = self.inventory_service.get_composite_items(self.product.id)
        for comp in components:
            row = self.comp_table.rowCount()
            self.comp_table.insertRow(row)
            self.comp_table.setItem(row, 0, QTableWidgetItem(str(comp["child_product_id"])))
            self.comp_table.setItem(row, 1, QTableWidgetItem(comp["child_name"]))
            self.comp_table.setItem(row, 2, QTableWidgetItem(str(comp["qty"])))

            remove_btn = QPushButton(_t("product_editor.btn_remove_component"))
            target_row = row
            remove_btn.clicked.connect(lambda checked, r=target_row: self._remove_component(r))
            self.comp_table.setCellWidget(row, 3, remove_btn)

    def _parse_decimal(self, text: str, fallback: str = "0") -> Decimal:
        """Safely parse a QLineEdit value to Decimal."""
        cleaned = text.strip()
        if not cleaned or cleaned in ("-", "."):
            return Decimal(fallback)
        return Decimal(cleaned)

    def save_product(self):
        """Validate all fields and create or update the product (with its bundle components) via InventoryService."""
        try:
            stock_qty = self._parse_decimal(self.stock_input.text())
            reorder_point = self._parse_decimal(self.reorder_input.text())
            preferred_qty = self._parse_decimal(self.preferred_qty_input.text())
        except Exception:
            QMessageBox.warning(self, _t("common.validation_error"), _t("product_editor.invalid_stock"))
            self.tabs.setCurrentIndex(1)
            self.stock_input.setFocus()
            return

        data = {
            "barcode": self.barcode_input.text().strip(),
            "name_en": self.name_en_input.text().strip(),
            "name_si": self.name_si_input.text().strip(),
            "name_ta": self.name_ta_input.text().strip(),
            "category_id": self.category_combo.currentData(),
            "price": self._parse_decimal(self.price_input.text()),
            "cost": self._parse_decimal(self.cost_input.text()),
            "stock_qty": stock_qty,
            "reorder_point": reorder_point,
            "preferred_qty": preferred_qty,
            "default_supplier_id": self.supplier_combo.currentData(),
            "unit_id": self.unit_combo.currentData(),
            "is_weighted": self.weighted_check.isChecked(),
            "is_service": self.service_check.isChecked(),
            "price_change_allowed": self.price_change_allowed_check.isChecked(),
            "is_age_restricted": self.age_restricted_check.isChecked(),
            "image_path": self.current_image_path,
            "is_active": True,
        }

        if not data["name_en"]:
            QMessageBox.warning(self, _t("common.validation_error"), _t("product_editor.name_required"))
            self.tabs.setCurrentIndex(0)
            self.name_en_input.setFocus()
            return

        if not data["barcode"] and not (self._auto_barcode and not self.product):
            QMessageBox.warning(self, _t("common.validation_error"), _t("product_editor.barcode_required"))
            self.tabs.setCurrentIndex(0)
            self.barcode_input.setFocus()
            return

        if data["price"] <= 0:
            QMessageBox.warning(self, _t("common.validation_error"), _t("product_editor.price_required"))
            self.tabs.setCurrentIndex(0)
            self.price_input.setFocus()
            return

        components = []
        for row in range(self.comp_table.rowCount()):
            child_id = int(self.comp_table.item(row, 0).text())
            qty = Decimal(self.comp_table.item(row, 2).text())
            components.append({"child_product_id": child_id, "qty": qty})

        data["components"] = components

        try:
            if self.product:
                self.inventory_service.update_product(self.product.id, data)
            else:
                if data["barcode"] and self.inventory_service.get_product_by_barcode(data["barcode"]):
                    QMessageBox.warning(
                        self,
                        _t("product_editor.duplicate_title"),
                        _t("product_editor.barcode_exists", barcode=data["barcode"]),
                    )
                    self.tabs.setCurrentIndex(0)
                    self.barcode_input.setFocus()
                    return
                self.inventory_service.create_product(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
