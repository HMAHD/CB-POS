from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QDoubleValidator, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.config import Config
from cbpos.core.models import Product
from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import get_currency_symbol
from cbpos.i18n import _t
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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_product)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
        self.barcode_input.setPlaceholderText(_t("product_editor.barcode_placeholder"))

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
        layout = QVBoxLayout(self.tab_inventory)
        layout.setSpacing(10)

        # Stock group — QLineEdit instead of QDoubleSpinBox for clean
        # rendering (QDoubleSpinBox +/- buttons break under QSS)
        grp_stock = QGroupBox(_t("product_editor.group_stock"))
        form_stock = QFormLayout(grp_stock)
        form_stock.setVerticalSpacing(10)
        form_stock.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        stock_validator = QDoubleValidator(-10000.0, 1000000.0, 3)
        reorder_validator = QDoubleValidator(0.0, 10000.0, 3)

        self.stock_input = QLineEdit()
        self.stock_input.setPlaceholderText("0.000")
        self.stock_input.setValidator(stock_validator)

        self.reorder_input = QLineEdit()
        self.reorder_input.setPlaceholderText("0.000")
        self.reorder_input.setValidator(reorder_validator)

        self.preferred_qty_input = QLineEdit()
        self.preferred_qty_input.setPlaceholderText("0.000")
        self.preferred_qty_input.setValidator(reorder_validator)

        form_stock.addRow(_t("product_editor.stock_qty"), self.stock_input)
        form_stock.addRow(_t("product_editor.reorder_point"), self.reorder_input)
        form_stock.addRow(_t("product_editor.preferred_qty"), self.preferred_qty_input)

        layout.addWidget(grp_stock)

        # Supplier + Unit row — side by side to save vertical space
        sup_unit_layout = QHBoxLayout()
        sup_unit_layout.setSpacing(10)

        grp_supplier = QGroupBox(_t("product_editor.group_supplier"))
        supplier_layout = QVBoxLayout(grp_supplier)
        self.supplier_combo = QComboBox()
        self.supplier_combo.addItem(_t("product_editor.no_default_supplier"), None)
        for supplier in self.suppliers:
            self.supplier_combo.addItem(supplier.company_name, supplier.id)
        supplier_layout.addWidget(self.supplier_combo)
        sup_unit_layout.addWidget(grp_supplier)

        grp_unit = QGroupBox(_t("product_editor.group_uom"))
        unit_inner = QVBoxLayout(grp_unit)
        self.unit_combo = QComboBox()
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
        type_layout.setContentsMargins(12, 12, 12, 8)
        type_layout.setSpacing(6)

        row_weighted = QHBoxLayout()
        row_weighted.setSpacing(6)
        self.weighted_check = QCheckBox(_t("product_editor.weighted_item"))
        row_weighted.addWidget(self.weighted_check)
        self.weighted_hint = QLabel(_t("product_editor.weighted_hint"))
        self.weighted_hint.setObjectName("ToggleHint")
        row_weighted.addWidget(self.weighted_hint)
        row_weighted.addStretch()
        type_layout.addLayout(row_weighted)

        row_service = QHBoxLayout()
        row_service.setSpacing(6)
        self.service_check = QCheckBox(_t("product_editor.service_item"))
        row_service.addWidget(self.service_check)
        self.service_hint = QLabel(_t("product_editor.service_hint"))
        self.service_hint.setObjectName("ToggleHint")
        row_service.addWidget(self.service_hint)
        row_service.addStretch()
        type_layout.addLayout(row_service)

        row_price_change = QHBoxLayout()
        row_price_change.setSpacing(6)
        self.price_change_allowed_check = QCheckBox(_t("product_editor.price_change_allowed"))
        self.price_change_allowed_check.setChecked(True)
        row_price_change.addWidget(self.price_change_allowed_check)
        self.price_change_hint = QLabel(_t("product_editor.price_change_hint"))
        self.price_change_hint.setObjectName("ToggleHint")
        row_price_change.addWidget(self.price_change_hint)
        row_price_change.addStretch()
        type_layout.addLayout(row_price_change)

        row_age_restricted = QHBoxLayout()
        row_age_restricted.setSpacing(6)
        self.age_restricted_check = QCheckBox(_t("product_editor.age_restricted"))
        row_age_restricted.addWidget(self.age_restricted_check)
        self.age_restricted_hint = QLabel(_t("product_editor.age_restricted_hint"))
        self.age_restricted_hint.setObjectName("ToggleHint")
        row_age_restricted.addWidget(self.age_restricted_hint)
        row_age_restricted.addStretch()
        type_layout.addLayout(row_age_restricted)

        layout.addWidget(grp_type)
        layout.addStretch()

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
            "image_path": getattr(self, "current_image_path", None),
            "is_active": True,
        }

        if not data["name_en"]:
            QMessageBox.warning(self, _t("common.validation_error"), _t("product_editor.name_required"))
            self.tabs.setCurrentIndex(0)
            self.name_en_input.setFocus()
            return

        if not data["barcode"]:
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
                if self.inventory_service.get_product_by_barcode(data["barcode"]):
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
