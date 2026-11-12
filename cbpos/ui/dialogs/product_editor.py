from decimal import ROUND_HALF_UP, Decimal

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
from cbpos.core.utils.validators import ProductValidator
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.layout_helpers import protect_vertical_sizing
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.form_card import FormCard
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)
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
        self.inventory_service = InventoryService()
        if product and getattr(product, "id", None):
            fresh_product = self.inventory_service.get_product(product.id)
            self.product = fresh_product or product
        else:
            self.product = product
        self.loaded_version = getattr(self.product, "version_id", None) if self.product else None

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

        # Tab 5: Warranty (#821)
        from cbpos.core.services.warranty_service import WarrantyService

        if WarrantyService.is_enabled():
            self.tab_warranty = QWidget()
            self.setup_warranty_tab()
            self.tabs.addTab(self.tab_warranty, _t("product_editor.tab_warranty"))

        layout.addWidget(self.tabs)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.save_product,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)
        protect_vertical_sizing(self)

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

        cost_layout = QHBoxLayout()
        cost_layout.setSpacing(6)
        cost_layout.addWidget(self.cost_input)

        if self.product:
            self.cost_input.setReadOnly(True)
            self.cost_input.setToolTip(_t("product.cost_avco_tooltip"))
            self.btn_set_cost = QPushButton(_t("product_editor.btn_set_cost"))
            self.btn_set_cost.setObjectName("BtnSetCost")
            self.btn_set_cost.clicked.connect(self._open_set_cost)
            cost_layout.addWidget(self.btn_set_cost)

        layout.addRow(_t("product_editor.name_en"), self.name_en_input)
        layout.addRow(_t("product_editor.name_si"), self.name_si_input)
        layout.addRow(_t("product_editor.name_ta"), self.name_ta_input)
        layout.addRow(_t("product_editor.barcode"), self.barcode_input)
        layout.addRow(_t("product_editor.category"), self.category_combo)
        layout.addRow(_t("product_editor.selling_price"), self.price_input)
        layout.addRow(_t("product_editor.cost_price"), cost_layout)

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

        stock_box = QHBoxLayout()
        stock_box.setSpacing(6)
        stock_box.addWidget(self.stock_input)

        if self.product:
            self.stock_input.setReadOnly(True)
            self.btn_adjust_stock = QPushButton(_t("product_editor.btn_adjust"))
            self.btn_adjust_stock.setObjectName("BtnAdjustStock")
            self.btn_adjust_stock.clicked.connect(self._open_stock_adjustment)
            stock_box.addWidget(self.btn_adjust_stock)

        col_stock.addLayout(stock_box)
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

        # Supplier + Unit row — clean 2-column FormCard with top field labels
        card_supplier_unit = FormCard()
        sup_unit_layout = QHBoxLayout()
        sup_unit_layout.setContentsMargins(0, 0, 0, 0)
        sup_unit_layout.setSpacing(12)

        col_supplier = QVBoxLayout()
        col_supplier.setSpacing(4)
        lbl_supplier = QLabel(_t("product_editor.group_supplier"))
        lbl_supplier.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.supplier_combo = QComboBox()
        self.supplier_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.supplier_combo.addItem(_t("product_editor.no_default_supplier"), None)
        for supplier in self.suppliers:
            self.supplier_combo.addItem(supplier.company_name, supplier.id)
        col_supplier.addWidget(lbl_supplier)
        col_supplier.addWidget(self.supplier_combo)
        sup_unit_layout.addLayout(col_supplier, 1)

        col_unit = QVBoxLayout()
        col_unit.setSpacing(4)
        lbl_unit = QLabel(_t("product_editor.group_uom"))
        lbl_unit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.unit_combo = QComboBox()
        self.unit_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.unit_combo.addItem(_t("product_editor.no_unit"), None)
        from cbpos.core.services.unit_service import UnitService

        for unit in UnitService.get_all():
            self.unit_combo.addItem(f"{unit.name} ({unit.abbreviation})", unit.id)
        col_unit.addWidget(lbl_unit)
        col_unit.addWidget(self.unit_combo)
        sup_unit_layout.addLayout(col_unit, 1)

        card_supplier_unit.add_layout(sup_unit_layout)
        layout.addWidget(card_supplier_unit)

        # Item type group — checkbox + inline hint with clear separation
        grp_type = QGroupBox(_t("product_editor.group_item_type"))
        type_layout = QVBoxLayout(grp_type)
        type_layout.setContentsMargins(12, 12, 12, 12)
        type_layout.setSpacing(8)

        # 1. Weighted
        row_weighted = QHBoxLayout()
        row_weighted.setSpacing(0)
        self.weighted_check = QCheckBox(_t("product_editor.weighted_item"))
        self.weighted_check.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row_weighted.addWidget(self.weighted_check, 0, Qt.AlignmentFlag.AlignVCenter)
        row_weighted.addSpacing(20)
        self.weighted_hint = QLabel(_t("product_editor.weighted_hint"))
        self.weighted_hint.setObjectName("ToggleHint")
        self.weighted_hint.setWordWrap(True)
        self.weighted_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_weighted.addWidget(self.weighted_hint, 1, Qt.AlignmentFlag.AlignVCenter)
        type_layout.addLayout(row_weighted)

        # 2. Service
        row_service = QHBoxLayout()
        row_service.setSpacing(0)
        self.service_check = QCheckBox(_t("product_editor.service_item"))
        self.service_check.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row_service.addWidget(self.service_check, 0, Qt.AlignmentFlag.AlignVCenter)
        row_service.addSpacing(20)
        self.service_hint = QLabel(_t("product_editor.service_hint"))
        self.service_hint.setObjectName("ToggleHint")
        self.service_hint.setWordWrap(True)
        self.service_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_service.addWidget(self.service_hint, 1, Qt.AlignmentFlag.AlignVCenter)
        type_layout.addLayout(row_service)

        # 3. Price change
        row_price_change = QHBoxLayout()
        row_price_change.setSpacing(0)
        self.price_change_allowed_check = QCheckBox(_t("product_editor.price_change_allowed"))
        self.price_change_allowed_check.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.price_change_allowed_check.setChecked(True)
        row_price_change.addWidget(self.price_change_allowed_check, 0, Qt.AlignmentFlag.AlignVCenter)
        row_price_change.addSpacing(20)
        self.price_change_hint = QLabel(_t("product_editor.price_change_hint"))
        self.price_change_hint.setObjectName("ToggleHint")
        self.price_change_hint.setWordWrap(True)
        self.price_change_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_price_change.addWidget(self.price_change_hint, 1, Qt.AlignmentFlag.AlignVCenter)
        type_layout.addLayout(row_price_change)

        # 4. Age restricted
        row_age_restricted = QHBoxLayout()
        row_age_restricted.setSpacing(0)
        self.age_restricted_check = QCheckBox(_t("product_editor.age_restricted"))
        self.age_restricted_check.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row_age_restricted.addWidget(self.age_restricted_check, 0, Qt.AlignmentFlag.AlignVCenter)
        row_age_restricted.addSpacing(20)
        self.age_restricted_hint = QLabel(_t("product_editor.age_restricted_hint"))
        self.age_restricted_hint.setObjectName("ToggleHint")
        self.age_restricted_hint.setWordWrap(True)
        self.age_restricted_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_age_restricted.addWidget(self.age_restricted_hint, 1, Qt.AlignmentFlag.AlignVCenter)
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
        self.btn_add_component.setProperty("class", "primary")
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
        configure_table_columns(
            self.comp_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,
                1: QHeaderView.ResizeMode.Stretch,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        align_numeric_headers(self.comp_table, (2,))
        attach_table_empty_state(self.comp_table, Icons.INVENTORY, "common.no_items")
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

        with batch_table_update(self.comp_table):
            row = self.comp_table.rowCount()
            self.comp_table.insertRow(row)
            self.comp_table.setItem(row, 0, QTableWidgetItem(str(product.id)))
            self.comp_table.setItem(row, 1, QTableWidgetItem(product.name_en))
            qty_item = QTableWidgetItem(str(qty))
            qty_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.comp_table.setItem(row, 2, qty_item)

            remove_btn = QPushButton(_t("product_editor.btn_remove_component"))
            remove_btn.setProperty("class", "danger")
            remove_btn.clicked.connect(self._on_remove_component_clicked)
            self.comp_table.setCellWidget(row, 3, remove_btn)

        self.comp_barcode_input.clear()
        self.comp_barcode_input.setFocus()

    def _on_remove_component_clicked(self) -> None:
        """Handle component removal from sender button click without lambda closure."""
        sender = self.sender()
        if sender:
            for r in range(self.comp_table.rowCount()):
                if self.comp_table.cellWidget(r, 3) is sender:
                    self.comp_table.removeRow(r)
                    break

    def _remove_component(self, row: int) -> None:
        """Remove a component row by index."""
        if row < self.comp_table.rowCount():
            self.comp_table.removeRow(row)

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
        self.btn_clear_img.setProperty("class", "secondary")
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

    def setup_warranty_tab(self):
        """Build the Warranty tab: override mode (INHERIT/NONE/POLICY), policy combo, and live preview."""
        layout = QFormLayout(self.tab_warranty)
        layout.setVerticalSpacing(14)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.setContentsMargins(16, 16, 16, 16)

        self.warranty_override_combo = QComboBox()
        self.warranty_override_combo.addItem(_t("product_editor.warranty_inherit"), "INHERIT")
        self.warranty_override_combo.addItem(_t("product_editor.warranty_none"), "NONE")
        self.warranty_override_combo.addItem(_t("product_editor.warranty_policy"), "POLICY")
        layout.addRow(_t("product_editor.warranty_mode"), self.warranty_override_combo)

        self.warranty_policy_combo = QComboBox()
        self.warranty_policy_combo.addItem(_t("product_editor.warranty_select_policy"), None)
        self._load_warranty_policies()
        layout.addRow(_t("warranty.policies"), self.warranty_policy_combo)

        self.lbl_warranty_preview = QLabel()
        self.lbl_warranty_preview.setWordWrap(True)
        self.lbl_warranty_preview.setProperty("class", "muted")
        layout.addRow(_t("common.preview", default="Preview:"), self.lbl_warranty_preview)

        self.warranty_override_combo.currentIndexChanged.connect(self._on_warranty_mode_changed)
        self.warranty_policy_combo.currentIndexChanged.connect(self._update_warranty_preview)
        self.category_combo.currentIndexChanged.connect(self._update_warranty_preview)
        self.weighted_check.toggled.connect(self._on_weighted_toggled_warranty)

        self._on_warranty_mode_changed()

    def _load_warranty_policies(self):
        from cbpos.core.services.warranty_service import WarrantyService

        policies = WarrantyService.list_policies(include_inactive=False)
        for pol in policies:
            self.warranty_policy_combo.addItem(pol.get_display_name(), pol.id)

        # If product already assigned an inactive policy, load it so it is visible
        if self.product and getattr(self.product, "warranty_policy_id", None):
            pid = self.product.warranty_policy_id
            if self.warranty_policy_combo.findData(pid) < 0:
                inactive_pol = WarrantyService.get_policy(pid)
                if inactive_pol:
                    self.warranty_policy_combo.addItem(
                        f"{inactive_pol.get_display_name()} ({_t('warranty.inactive')})",
                        inactive_pol.id,
                    )

    def _on_warranty_mode_changed(self):
        mode = self.warranty_override_combo.currentData()
        self.warranty_policy_combo.setEnabled(mode == "POLICY")
        self._update_warranty_preview()

    def _on_weighted_toggled_warranty(self, checked: bool):
        if hasattr(self, "warranty_override_combo"):
            if checked:
                self.warranty_override_combo.setEnabled(False)
                self.warranty_policy_combo.setEnabled(False)
            else:
                self.warranty_override_combo.setEnabled(True)
                self._on_warranty_mode_changed()
            self._update_warranty_preview()

    def _update_warranty_preview(self):
        if not hasattr(self, "lbl_warranty_preview"):
            return

        if self.weighted_check.isChecked():
            self.lbl_warranty_preview.setText(_t("product_editor.warranty_weighted_hint"))
            return

        from datetime import date
        from decimal import Decimal

        from cbpos.core.models import Product
        from cbpos.core.services.warranty_service import WarrantyService
        from cbpos.core.utils.formatters import format_date

        mode = self.warranty_override_combo.currentData()
        if mode == "NONE":
            self.lbl_warranty_preview.setText(_t("product_editor.warranty_preview_none"))
            return

        if mode == "POLICY":
            policy_id = self.warranty_policy_combo.currentData()
            if not policy_id:
                self.lbl_warranty_preview.setText(_t("product_editor.warranty_select_policy"))
                return
            policy = WarrantyService.get_policy(policy_id)
        else:  # INHERIT
            cat_id = self.category_combo.currentData()
            dummy = Product(
                barcode="TEMP",
                name_en="Temp",
                category_id=cat_id,
                warranty_override="INHERIT",
                price=Decimal("0.00"),
            )
            policy = WarrantyService.resolve_policy(dummy)

        if not policy:
            self.lbl_warranty_preview.setText(_t("product_editor.warranty_preview_none"))
        else:
            today = date.today()
            end_date = WarrantyService.compute_end_date(today, policy.duration, policy.duration_unit)
            self.lbl_warranty_preview.setText(
                _t(
                    "product_editor.warranty_preview_covered",
                    sale_date=format_date(today),
                    end_date=format_date(end_date),
                    policy_name=policy.get_display_name(),
                )
            )

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

        self.price_input.setText(
            format(Decimal(str(self.product.price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
        )
        self.cost_input.setText(
            format(Decimal(str(self.product.cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
        )

        _q = Decimal("0.001")
        self.stock_input.setText(
            "" if self.product.stock_qty is None else format(Decimal(str(self.product.stock_qty)).quantize(_q), "f")
        )
        self.reorder_input.setText(
            ""
            if self.product.reorder_point is None
            else format(Decimal(str(self.product.reorder_point)).quantize(_q), "f")
        )
        self.preferred_qty_input.setText(
            ""
            if self.product.preferred_qty is None
            else format(Decimal(str(self.product.preferred_qty)).quantize(_q), "f")
        )
        self.weighted_check.setChecked(bool(self.product.is_weighted))
        self.service_check.setChecked(bool(self.product.is_service))
        self.price_change_allowed_check.setChecked(bool(self.product.price_change_allowed))
        self.age_restricted_check.setChecked(bool(self.product.is_age_restricted))

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
        with batch_table_update(self.comp_table):
            TableItem = QTableWidgetItem
            num_align = NUMERIC_ALIGNMENT
            set_item = self.comp_table.setItem
            insert_row = self.comp_table.insertRow
            set_cell_widget = self.comp_table.setCellWidget
            btn_remove_text = _t("product_editor.btn_remove_component")
            on_remove = self._on_remove_component_clicked

            for comp in components:
                row = self.comp_table.rowCount()
                insert_row(row)
                set_item(row, 0, TableItem(str(comp["child_product_id"])))
                set_item(row, 1, TableItem(comp["child_name"]))
                qty_item = TableItem(str(comp["qty"]))
                qty_item.setTextAlignment(num_align)
                set_item(row, 2, qty_item)

                remove_btn = QPushButton(btn_remove_text)
                remove_btn.setProperty("class", "danger")
                remove_btn.clicked.connect(on_remove)
                set_cell_widget(row, 3, remove_btn)

        # Load warranty
        if hasattr(self, "warranty_override_combo"):
            idx = self.warranty_override_combo.findData(self.product.warranty_override or "INHERIT")
            if idx >= 0:
                self.warranty_override_combo.setCurrentIndex(idx)
            if self.product.warranty_policy_id:
                w_idx = self.warranty_policy_combo.findData(self.product.warranty_policy_id)
                if w_idx >= 0:
                    self.warranty_policy_combo.setCurrentIndex(w_idx)
            self._on_warranty_mode_changed()

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

        # #901: Shared validation via ProductValidator
        price_err = ProductValidator.validate_price(data["price"])
        if price_err:
            QMessageBox.warning(self, _t("common.validation_error"), _t("product_editor.price_required"))
            self.tabs.setCurrentIndex(0)
            self.price_input.setFocus()
            return

        cost_err = ProductValidator.validate_cost(data.get("cost"))
        if cost_err:
            QMessageBox.warning(self, _t("common.validation_error"), cost_err)
            self.tabs.setCurrentIndex(0)
            self.cost_input.setFocus()
            return

        stock_err = ProductValidator.validate_stock(data.get("stock_qty"))
        if stock_err:
            QMessageBox.warning(self, _t("common.validation_error"), stock_err)
            self.tabs.setCurrentIndex(1)
            self.stock_input.setFocus()
            return

        components = []
        for row in range(self.comp_table.rowCount()):
            child_id = int(self.comp_table.item(row, 0).text())
            qty = Decimal(self.comp_table.item(row, 2).text())
            components.append({"child_product_id": child_id, "qty": qty})

        data["components"] = components

        if hasattr(self, "tab_warranty"):
            override = self.warranty_override_combo.currentData() or "INHERIT"
            policy_id = self.warranty_policy_combo.currentData() if override == "POLICY" else None
            if data.get("is_weighted") and override == "POLICY":
                QMessageBox.warning(self, _t("common.validation_error"), _t("product_editor.warranty_weighted_hint"))
                self.tabs.setCurrentWidget(self.tab_warranty)
                return
            if override == "POLICY" and not policy_id:
                QMessageBox.warning(self, _t("common.validation_error"), _t("product_editor.warranty_select_policy"))
                self.tabs.setCurrentWidget(self.tab_warranty)
                return
            data["warranty_override"] = override
            data["warranty_policy_id"] = policy_id
            data["serial_mode"] = getattr(self.product, "serial_mode", "OFF") if self.product else "OFF"

        try:
            if self.product:
                from cbpos.core.services.inventory_service import StaleProductError

                # Drop stock_qty and cost for updates to prevent overwriting (#862)
                data.pop("stock_qty", None)
                data.pop("cost", None)
                try:
                    self.inventory_service.update_product(self.product.id, data, expected_version=self.loaded_version)
                except StaleProductError:
                    QMessageBox.warning(
                        self,
                        _t("common.warning"),
                        _t("product.modified_elsewhere"),
                    )
                    return
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

    def _open_stock_adjustment(self):
        """Open StockAdjustmentDialog for this product and update stock display on success (#862)."""
        from cbpos.ui.dialogs.stock_adjustment_dialog import StockAdjustmentDialog

        dlg = StockAdjustmentDialog(self.product, inventory_service=self.inventory_service, parent=self)
        if dlg.exec():
            fresh = self.inventory_service.get_product(self.product.id)
            if fresh:
                self.product = fresh
                self.loaded_version = fresh.version_id
                _q = Decimal("0.001")
                self.stock_input.setText(
                    ""
                    if self.product.stock_qty is None
                    else format(Decimal(str(self.product.stock_qty)).quantize(_q), "f")
                )

    def _open_set_cost(self):
        """Prompt to override cost manually with permission check (#862)."""
        from decimal import ROUND_HALF_UP, Decimal

        from PyQt6.QtWidgets import QInputDialog

        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        user = check_permission_with_override(Permissions.INVENTORY_SET_COST, self)
        if not user:
            return

        current_val = float(self.product.cost or 0)
        new_val, ok = QInputDialog.getDouble(
            self,
            _t("product_editor.dialog_set_cost_title"),
            _t("product_editor.dialog_set_cost_prompt", name=self.product.name_en),
            value=current_val,
            min=0.0,
            max=1000000.0,
            decimals=2,
        )
        if ok:
            try:
                new_cost_dec = Decimal(f"{new_val:.2f}")
                updated = self.inventory_service.set_cost(self.product.id, new_cost_dec, user.id)
                self.product = updated
                self.loaded_version = updated.version_id
                self.cost_input.setText(
                    format(Decimal(str(self.product.cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
                )
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))
