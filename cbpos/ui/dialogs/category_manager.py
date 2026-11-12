"""
Dialog for managing product categories (CRUD) with tree view and inline editing.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from cbpos.core.models import Category
from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.styles.style_helpers import set_color_swatch
from cbpos.ui.widgets.table_helpers import configure_table_columns
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)

CATEGORY_ID_ROLE = Qt.ItemDataRole.UserRole


def _color_icon(hex_color: str, size: int = 16) -> QIcon:
    """Create a small colored square icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(hex_color))
    return QIcon(pixmap)


class CategoryManagerDialog(QDialog):
    """Category manager with tree view, inline form, and subcategory support."""

    def __init__(self, parent=None):
        """Initialize the dialog and load the category tree."""
        super().__init__(parent)
        self.setWindowTitle(_t("category_manager.title"))
        self.setMinimumSize(640, 500)
        self.resize(700, 540)
        self.setObjectName("CategoryManagerDialog")
        self.selected_color = "#00BCEB"
        self._editing_id = None
        self._setup_ui()
        self._load_tree()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Left: Tree ──
        left = QVBoxLayout()
        left.setSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_t("category_manager.col_category"), _t("category_manager.col_products")])
        configure_table_columns(
            self.tree.header(),
            {
                0: QHeaderView.ResizeMode.Stretch,  # Category - needs the room
                1: QHeaderView.ResizeMode.ResizeToContents,  # Products
            },
        )
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.tree)

        layout.addLayout(left, 2)

        # ── Right: Form + Actions ──
        right = QVBoxLayout()
        right.setSpacing(10)

        # Form
        form_group = QGroupBox(_t("category_manager.details_group"))
        form_layout = QFormLayout(form_group)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(10)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText(_t("category_manager.name_placeholder"))
        form_layout.addRow(_t("category_manager.name_label"), self.txt_name)

        self.combo_parent = QComboBox()
        self.combo_parent.setToolTip(_t("category.parent_hint"))
        form_layout.addRow(_t("category_manager.parent_label"), self.combo_parent)

        self.lbl_parent_hint = QLabel(_t("category.parent_hint"))
        self.lbl_parent_hint.setProperty("class", "muted")
        self.lbl_parent_hint.setWordWrap(True)
        form_layout.addRow("", self.lbl_parent_hint)

        # Color picker row
        color_row = QHBoxLayout()
        self.lbl_color = QLabel()
        self.lbl_color.setFixedSize(32, 32)
        self._update_color_preview()
        self.btn_pick_color = QPushButton(_t("category_manager.pick_color"))
        self.btn_pick_color.clicked.connect(self._pick_color)
        color_row.addWidget(self.lbl_color)
        color_row.addWidget(self.btn_pick_color)
        color_row.addStretch()
        form_layout.addRow(_t("category_manager.color_label"), color_row)

        # Tax exemption options
        self.chk_vat_exempt = QCheckBox(_t("category_manager.vat_exempt"))
        self.chk_sscl_exempt = QCheckBox(_t("category_manager.sscl_exempt"))
        self.lbl_tax_exempt_hint = QLabel(_t("category_manager.tax_exemptions_disabled_hint"))
        self.lbl_tax_exempt_hint.setProperty("class", "muted")
        self.lbl_tax_exempt_hint.setWordWrap(True)

        tax_exemptions_enabled = bool(ConfigService.get("item_tax_exemptions"))
        if tax_exemptions_enabled:
            form_layout.addRow("", self.chk_vat_exempt)
            form_layout.addRow("", self.chk_sscl_exempt)
            self.lbl_tax_exempt_hint.hide()
        else:
            self.chk_vat_exempt.hide()
            self.chk_sscl_exempt.hide()
            form_layout.addRow("", self.lbl_tax_exempt_hint)

        from cbpos.core.services.warranty_service import WarrantyService

        if WarrantyService.is_enabled():
            self.combo_warranty = QComboBox()
            self.combo_warranty.addItem(_t("category_manager.warranty_none"), None)
            for pol in WarrantyService.list_policies(include_inactive=False):
                self.combo_warranty.addItem(pol.get_display_name(), pol.id)
            form_layout.addRow(_t("category_manager.default_warranty"), self.combo_warranty)

        right.addWidget(form_group)

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_save = QPushButton(_t("category_manager.save_new"))
        self.btn_save.setProperty("class", "primary")
        self.btn_save.clicked.connect(self._save_category)
        btn_layout.addWidget(self.btn_save)

        self.btn_delete = QPushButton(_t("category_manager.delete_selected"))
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_category)
        btn_layout.addWidget(self.btn_delete)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        btn_layout.addWidget(sep)

        self.btn_clear = QPushButton(_t("category_manager.clear_new"))
        self.btn_clear.setProperty("class", "secondary")
        self.btn_clear.clicked.connect(self._clear_form)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()

        self.btn_close = QPushButton(_t("common.close"))
        self.btn_close.setProperty("class", "secondary")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        right.addLayout(btn_layout)

        layout.addLayout(right, 1)

    # ── Tree loading ──

    def _load_tree(self) -> None:
        """Reload the full category tree from service."""
        self.tree.clear()
        categories = CategoryService.get_top_level_with_subcategories_and_products()

        for cat in categories:
            item = self._make_tree_item(cat)
            self.tree.addTopLevelItem(item)
            for sub in sorted(cat.subcategories, key=lambda c: c.name):
                child = self._make_tree_item(sub)
                item.addChild(child)

        self.tree.expandAll()
        self._populate_parent_combo()

    def _make_tree_item(self, cat: Category) -> QTreeWidgetItem:
        product_count = len(cat.products) if cat.products else 0
        item = QTreeWidgetItem([cat.name, str(product_count)])
        item.setData(0, CATEGORY_ID_ROLE, cat.id)
        item.setIcon(0, _color_icon(cat.color or "#FFFFFF"))
        return item

    def _populate_parent_combo(self, exclude_id: int = None) -> None:
        """Populate parent combo with top-level categories only (#921)."""
        self.combo_parent.clear()
        self.combo_parent.addItem(_t("category_manager.none_top_level"), None)

        top_cats = CategoryService.get_top_level()

        for c in top_cats:
            if c.id != exclude_id:
                self.combo_parent.addItem(_color_icon(c.color or "#FFFFFF"), c.name, c.id)

    # ── Selection ──

    def _on_selection_changed(self, current: QTreeWidgetItem, _prev: QTreeWidgetItem) -> None:
        has_selection = current is not None
        self.btn_delete.setEnabled(has_selection)

        if not has_selection:
            self._editing_id = None
            return

        cat_id = current.data(0, CATEGORY_ID_ROLE)
        self._editing_id = cat_id

        cat = CategoryService.get_by_id(cat_id)
        if not cat:
            return

        self.txt_name.setText(cat.name)
        self.selected_color = cat.color or "#00BCEB"
        self._update_color_preview()
        self.chk_vat_exempt.setChecked(bool(cat.tax_exempt))
        self.chk_sscl_exempt.setChecked(bool(cat.sscl_exempt))
        if hasattr(self, "combo_warranty"):
            assigned_id = getattr(cat, "default_warranty_policy_id", None)
            w_idx = self.combo_warranty.findData(assigned_id)
            if assigned_id and w_idx < 0:
                from cbpos.core.services.warranty_service import WarrantyService

                pol = WarrantyService.get_policy(assigned_id)
                if pol:
                    self.combo_warranty.addItem(f"{pol.get_display_name()} (inactive)", pol.id)
                    w_idx = self.combo_warranty.findData(assigned_id)
            self.combo_warranty.setCurrentIndex(max(0, w_idx))

        # Rebuild parent combo excluding self
        self._populate_parent_combo(exclude_id=cat_id)
        idx = self.combo_parent.findData(cat.parent_id)
        if idx >= 0:
            self.combo_parent.setCurrentIndex(idx)

        has_subcategories = bool(CategoryService.get_descendant_ids(cat_id))
        if has_subcategories:
            self.combo_parent.setEnabled(False)
            self.combo_parent.setToolTip(_t("category.has_children_locked"))
        else:
            self.combo_parent.setEnabled(True)
            self.combo_parent.setToolTip(_t("category.parent_hint"))

        self.btn_save.setText(_t("category_manager.update"))

    # ── Actions ──

    def _save_category(self) -> None:
        """Add or update a category based on current editing state."""
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, _t("common.validation_error"), _t("category_manager.name_required"))
            self.txt_name.setFocus()
            return

        parent_id = self.combo_parent.currentData()
        tax_exempt = self.chk_vat_exempt.isChecked()
        sscl_exempt = self.chk_sscl_exempt.isChecked()

        try:
            if self._editing_id:
                update_kwargs = {
                    "name": name,
                    "color": self.selected_color,
                    "parent_id": parent_id,
                    "tax_exempt": tax_exempt,
                    "sscl_exempt": sscl_exempt,
                }
                if hasattr(self, "combo_warranty"):
                    update_kwargs["default_warranty_policy_id"] = self.combo_warranty.currentData()
                CategoryService.update(self._editing_id, **update_kwargs)
            else:
                create_kwargs = {
                    "name": name,
                    "color": self.selected_color,
                    "parent_id": parent_id,
                    "tax_exempt": tax_exempt,
                    "sscl_exempt": sscl_exempt,
                }
                if hasattr(self, "combo_warranty"):
                    create_kwargs["default_warranty_policy_id"] = self.combo_warranty.currentData()
                CategoryService.create(**create_kwargs)
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
            return

        self._load_tree()
        self._clear_form()

    def _delete_category(self) -> None:
        current = self.tree.currentItem()
        if not current:
            return

        cat_id = current.data(0, CATEGORY_ID_ROLE)
        cat_name = current.text(0)

        descendant_ids = CategoryService.get_descendant_ids(cat_id)
        all_ids = {cat_id} | descendant_ids

        product_count = CategoryService.get_product_count_for_ids(all_ids)

        if product_count > 0:
            QMessageBox.warning(
                self,
                _t("category_manager.cannot_delete_title"),
                _t(
                    "category_manager.cannot_delete_msg",
                    name=cat_name,
                    count=product_count,
                ),
            )
            return

        sub_count = len(descendant_ids)
        msg = _t("category_manager.confirm_delete_msg", name=cat_name)
        if sub_count > 0:
            msg += "\n\n" + _t("category_manager.confirm_delete_sub", count=sub_count)

        reply = QMessageBox.question(
            self,
            _t("category_manager.confirm_delete_title"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            CategoryService.delete_with_descendants(cat_id)
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
            return

        self._load_tree()
        self._clear_form()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.selected_color), self, _t("category_manager.select_color"))
        if color.isValid():
            self.selected_color = color.name()
            self._update_color_preview()

    def _update_color_preview(self) -> None:
        """Update the color swatch label."""
        set_color_swatch(self.lbl_color, self.selected_color)

    def _clear_form(self) -> None:
        """Clear form and reset to 'add new' mode."""
        self._editing_id = None
        self.txt_name.clear()
        self.selected_color = "#00BCEB"
        self._update_color_preview()
        self.chk_vat_exempt.setChecked(False)
        self.chk_sscl_exempt.setChecked(False)
        if hasattr(self, "combo_warranty"):
            self.combo_warranty.setCurrentIndex(0)
        self.btn_save.setText(_t("category_manager.save_new"))
        self.btn_delete.setEnabled(False)
        self.tree.clearSelection()
        self.combo_parent.setEnabled(True)
        self.combo_parent.setToolTip(_t("category.parent_hint"))
        self._populate_parent_combo()
        self.txt_name.setFocus()
