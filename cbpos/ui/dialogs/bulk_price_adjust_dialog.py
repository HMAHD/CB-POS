"""Dialog for bulk adjusting price list prices with live margin preview (#544)."""

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.price_list_service import (
    BulkAdjustmentRule,
    BulkPreviewItem,
    PriceListService,
)
from cbpos.core.services.product_service import ProductService
from cbpos.core.utils.formatters import NO_VALUE, format_number, money_header
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, SUCCESS, status_color
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    configure_table_columns,
)
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

RULE_PERCENTAGE_OFF = "PERCENTAGE_OFF"
RULE_FIXED_OFF = "FIXED_OFF"
RULE_FIXED_MARKUP = "FIXED_MARKUP"
RULE_MARGIN_OVER_COST = "MARGIN_OVER_COST"

ROUND_EXACT = "EXACT"
ROUND_NEAREST_1 = "NEAREST_1"
ROUND_NEAREST_5 = "NEAREST_5"
ROUND_CHARM_99 = "CHARM_99"

SCOPE_SELECTED = "SELECTED"
SCOPE_CATEGORY = "CATEGORY"
SCOPE_ALL = "ALL"


class BulkPriceAdjustDialog(QDialog):
    """Dialog allowing users to calculate and apply bulk adjustments to a price list (#544)."""

    def __init__(
        self,
        price_list_id: int,
        price_list_name: str,
        selected_product_ids: list[int] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("BulkPriceAdjustDialog")
        self.resize(920, 680)

        self.price_list_id = price_list_id
        self.price_list_name = price_list_name
        self.selected_product_ids = selected_product_ids or []

        self.price_list_service = PriceListService()
        self.product_service = ProductService()

        self.current_preview_items: list[BulkPreviewItem] = []
        self.below_cost_count: int = 0
        self._categories: list = []

        self.init_ui()
        self.load_categories()
        self.retranslate_ui()
        install_wheel_guard(self)
        register_language_callback(self.retranslate_ui, owner=self)

        self.refresh_preview()

    def init_ui(self) -> None:
        """Construct controls, live preview table, and action buttons."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── Header ──
        header_frame = QFrame()
        header_frame.setObjectName("BulkAdjustHeaderFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 4)

        icon_label = QLabel()
        icon_label.setPixmap(Icons.get(Icons.PRICE_LIST, "#00BCEB").pixmap(24, 24))
        header_layout.addWidget(icon_label)

        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        header_layout.addWidget(self.lbl_title)

        header_layout.addStretch()

        self.lbl_list_badge = QLabel(self.price_list_name)
        self.lbl_list_badge.setObjectName("BulkPriceBadge")
        header_layout.addWidget(self.lbl_list_badge)
        main_layout.addWidget(header_frame)

        # ── Settings row (Scope & Rule cards side by side) ──
        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)

        # 1. Target Scope Group
        self.group_scope = QGroupBox()
        self.group_scope.setObjectName("BulkScopeGroup")
        scope_layout = QVBoxLayout(self.group_scope)
        scope_layout.setSpacing(8)

        self.radio_selected = QRadioButton()
        self.radio_selected.setObjectName("RadioScopeSelected")
        if self.selected_product_ids:
            self.radio_selected.setChecked(True)
        else:
            self.radio_selected.setEnabled(False)
        self.radio_selected.toggled.connect(self._on_scope_changed)
        scope_layout.addWidget(self.radio_selected)

        cat_row = QHBoxLayout()
        cat_row.setSpacing(6)
        self.radio_category = QRadioButton()
        self.radio_category.setObjectName("RadioScopeCategory")
        self.radio_category.toggled.connect(self._on_scope_changed)
        cat_row.addWidget(self.radio_category)

        self.combo_category = QComboBox()
        self.combo_category.setObjectName("ComboScopeCategory")
        self.combo_category.setEnabled(False)
        self.combo_category.currentIndexChanged.connect(self._on_category_changed)
        cat_row.addWidget(self.combo_category, 1)
        scope_layout.addLayout(cat_row)

        self.radio_all = QRadioButton()
        self.radio_all.setObjectName("RadioScopeAll")
        if not self.selected_product_ids:
            self.radio_all.setChecked(True)
        self.radio_all.toggled.connect(self._on_scope_changed)
        scope_layout.addWidget(self.radio_all)

        scope_layout.addStretch()
        settings_row.addWidget(self.group_scope, 1)

        # 2. Pricing Rule Group
        self.group_rule = QGroupBox()
        self.group_rule.setObjectName("BulkRuleGroup")
        rule_layout = QGridLayout(self.group_rule)
        rule_layout.setSpacing(8)

        self.lbl_rule_type = QLabel()
        rule_layout.addWidget(self.lbl_rule_type, 0, 0)
        self.combo_rule_type = QComboBox()
        self.combo_rule_type.setObjectName("ComboRuleType")
        self.combo_rule_type.addItem("", RULE_PERCENTAGE_OFF)
        self.combo_rule_type.addItem("", RULE_FIXED_OFF)
        self.combo_rule_type.addItem("", RULE_FIXED_MARKUP)
        self.combo_rule_type.addItem("", RULE_MARGIN_OVER_COST)
        self.combo_rule_type.currentIndexChanged.connect(self._on_rule_type_changed)
        rule_layout.addWidget(self.combo_rule_type, 0, 1)

        self.lbl_rule_val = QLabel()
        rule_layout.addWidget(self.lbl_rule_val, 1, 0)
        self.spin_value = QDoubleSpinBox()
        self.spin_value.setObjectName("SpinRuleValue")
        self.spin_value.setDecimals(2)
        self.spin_value.setRange(0.01, 999999.00)
        self.spin_value.setValue(10.00)
        self.spin_value.setSuffix(" %")
        self.spin_value.valueChanged.connect(self._on_value_changed)
        rule_layout.addWidget(self.spin_value, 1, 1)

        self.lbl_rounding = QLabel()
        rule_layout.addWidget(self.lbl_rounding, 2, 0)
        self.combo_rounding = QComboBox()
        self.combo_rounding.setObjectName("ComboRounding")
        self.combo_rounding.addItem("", ROUND_EXACT)
        self.combo_rounding.addItem("", ROUND_NEAREST_1)
        self.combo_rounding.addItem("", ROUND_NEAREST_5)
        self.combo_rounding.addItem("", ROUND_CHARM_99)
        self.combo_rounding.currentIndexChanged.connect(self._on_rounding_changed)
        rule_layout.addWidget(self.combo_rounding, 2, 1)

        settings_row.addWidget(self.group_rule, 1)
        main_layout.addLayout(settings_row)

        # ── Below Cost Warning Banner ──
        self.banner_below_cost = QLabel()
        self.banner_below_cost.setObjectName("BulkBelowCostBanner")
        self.banner_below_cost.setVisible(False)
        main_layout.addWidget(self.banner_below_cost)

        # ── Preview Table ──
        self.lbl_preview_header = QLabel()
        self.lbl_preview_header.setProperty("class", "bold")
        main_layout.addWidget(self.lbl_preview_header)

        self.table_preview = QTableWidget()
        self.table_preview.setObjectName("BulkPreviewTable")
        self.table_preview.setColumnCount(7)
        configure_table_columns(
            self.table_preview.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
                5: QHeaderView.ResizeMode.ResizeToContents,
                6: QHeaderView.ResizeMode.ResizeToContents,
            },
            stretch_last_section=False,
            minimum_section_size=60,
        )
        self.table_preview.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_preview.setAlternatingRowColors(True)
        self.table_preview.verticalHeader().setVisible(False)
        main_layout.addWidget(self.table_preview, 1)

        # ── Footer ──
        self.lbl_summary_stats = QLabel()
        self.lbl_summary_stats.setProperty("class", "muted")

        footer_layout, self.btn_apply, self.btn_cancel = make_dialog_footer(
            primary_key="pricelist.btn_apply_adjustments",
            on_primary=self.apply_and_accept,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnApplyAdjustments",
            left_widget=self.lbl_summary_stats,
        )
        main_layout.addLayout(footer_layout)

    def load_categories(self) -> None:
        """Fetch categories to populate the category selector."""
        self._categories = self.product_service.get_all_categories()
        self.combo_category.clear()
        for cat in self._categories:
            self.combo_category.addItem(cat.name, cat.id)

    def retranslate_ui(self) -> None:
        """Update localized text for all labels, radio buttons, and table headers."""
        self.setWindowTitle(_t("pricelist.bulk_title"))
        self.lbl_title.setText(_t("pricelist.bulk_title"))

        self.group_scope.setTitle(_t("pricelist.bulk_target_scope"))
        self.radio_selected.setText(_t("pricelist.scope_selected", count=len(self.selected_product_ids)))
        self.radio_category.setText(_t("pricelist.scope_category"))
        self.radio_all.setText(_t("pricelist.scope_all", count=self._get_total_product_count()))

        self.group_rule.setTitle(_t("pricelist.bulk_pricing_rule"))
        self.lbl_rule_type.setText(_t("pricelist.bulk_pricing_rule"))
        self.lbl_rule_val.setText(_t("pricelist.bulk_adjustment_value"))
        self.lbl_rounding.setText(_t("pricelist.bulk_rounding_options"))

        # Re-set combo text without changing current index
        idx_rule = self.combo_rule_type.currentIndex()
        self.combo_rule_type.setItemText(0, _t("pricelist.rule_percent_off"))
        self.combo_rule_type.setItemText(1, _t("pricelist.rule_fixed_off"))
        self.combo_rule_type.setItemText(2, _t("pricelist.rule_fixed_markup"))
        self.combo_rule_type.setItemText(3, _t("pricelist.rule_margin_cost"))
        if idx_rule >= 0:
            self.combo_rule_type.setCurrentIndex(idx_rule)

        idx_round = self.combo_rounding.currentIndex()
        self.combo_rounding.setItemText(0, _t("pricelist.rounding_exact"))
        self.combo_rounding.setItemText(1, _t("pricelist.rounding_nearest_1"))
        self.combo_rounding.setItemText(2, _t("pricelist.rounding_nearest_5"))
        self.combo_rounding.setItemText(3, _t("pricelist.rounding_charm_99"))
        if idx_round >= 0:
            self.combo_rounding.setCurrentIndex(idx_round)

        headers = [
            _t("pricelist.header_product"),
            _t("pricelist.header_category"),
            money_header(_t("pricelist.header_base_price")),
            money_header(_t("pricelist.header_list_price")),
            money_header(_t("pricelist.header_cost")),
            money_header(_t("pricelist.header_new_price")),
            _t("pricelist.header_margin"),
        ]
        self.table_preview.setHorizontalHeaderLabels(headers)
        align_numeric_headers(self.table_preview, (2, 3, 4, 5))

        self.lbl_preview_header.setText(_t("pricelist.preview_title", count=len(self.current_preview_items)))
        self.btn_apply.setText(_t("pricelist.btn_apply_adjustments"))
        self.btn_cancel.setText(_t("common.cancel"))

    def _get_total_product_count(self) -> int:
        try:
            return len(self.product_service.get_all_products())
        except Exception:
            return 0

    def _on_scope_changed(self) -> None:
        self.combo_category.setEnabled(self.radio_category.isChecked())
        self.refresh_preview()

    def _on_category_changed(self) -> None:
        if self.radio_category.isChecked():
            self.refresh_preview()

    def _on_rule_type_changed(self) -> None:
        rule_type = self.combo_rule_type.currentData()
        if rule_type in (RULE_PERCENTAGE_OFF, RULE_MARGIN_OVER_COST):
            self.spin_value.setPrefix("")
            self.spin_value.setSuffix(" %")
            self.spin_value.setRange(0.01, 1000.00)
        else:
            self.spin_value.setPrefix("Rs. ")
            self.spin_value.setSuffix("")
            self.spin_value.setRange(0.01, 999999.00)
        self.refresh_preview()

    def _on_value_changed(self) -> None:
        self.refresh_preview()

    def _on_rounding_changed(self) -> None:
        self.refresh_preview()

    def get_current_rule(self) -> BulkAdjustmentRule:
        """Construct a BulkAdjustmentRule from the current UI state."""
        rule_type = self.combo_rule_type.currentData() or RULE_PERCENTAGE_OFF
        value = Decimal(str(self.spin_value.value()))
        rounding = self.combo_rounding.currentData() or ROUND_EXACT

        if self.radio_selected.isChecked():
            scope = SCOPE_SELECTED
            product_ids = self.selected_product_ids
            category_id = None
        elif self.radio_category.isChecked():
            scope = SCOPE_CATEGORY
            category_id = self.combo_category.currentData()
            product_ids = None
        else:
            scope = SCOPE_ALL
            category_id = None
            product_ids = None

        return BulkAdjustmentRule(
            rule_type=rule_type,
            value=value,
            rounding=rounding,
            scope=scope,
            category_id=category_id,
            product_ids=product_ids,
        )

    def refresh_preview(self) -> None:
        """Calculate and render live preview items without persisting anything."""
        rule = self.get_current_rule()
        try:
            self.current_preview_items = self.price_list_service.calculate_preview(self.price_list_id, rule)
        except Exception:
            self.current_preview_items = []

        self.below_cost_count = sum(1 for item in self.current_preview_items if item.is_below_cost)

        # Update warning banner
        if self.below_cost_count > 0:
            self.banner_below_cost.setText(f"⚠️  {_t('pricelist.below_cost_warning_msg', count=self.below_cost_count)}")
            self.banner_below_cost.setVisible(True)
        else:
            self.banner_below_cost.setVisible(False)

        # Populate table
        self.table_preview.setRowCount(0)
        for item in self.current_preview_items:
            row = self.table_preview.rowCount()
            self.table_preview.insertRow(row)

            # 0: Product Name
            self.table_preview.setItem(row, 0, QTableWidgetItem(item.product_name))

            # 1: Category Name
            cat_item = QTableWidgetItem(item.category_name or NO_VALUE)
            self.table_preview.setItem(row, 1, cat_item)

            # 2: Base Price
            base_item = QTableWidgetItem(format_number(item.base_price, 2))
            base_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table_preview.setItem(row, 2, base_item)

            # 3: Old List Price
            old_str = format_number(item.old_list_price, 2) if item.old_list_price is not None else NO_VALUE
            old_item = QTableWidgetItem(old_str)
            old_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table_preview.setItem(row, 3, old_item)

            # 4: Cost
            cost_str = format_number(item.cost, 2) if item.cost > 0 else NO_VALUE
            cost_item = QTableWidgetItem(cost_str)
            cost_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table_preview.setItem(row, 4, cost_item)

            # 5: New Price
            new_item = QTableWidgetItem(format_number(item.new_list_price, 2))
            new_item.setTextAlignment(NUMERIC_ALIGNMENT)
            if item.is_below_cost:
                new_item.setForeground(status_color(DANGER))
            else:
                new_item.setForeground(status_color(SUCCESS))
            self.table_preview.setItem(row, 5, new_item)

            # 6: Margin / Status
            if item.cost > 0:
                if item.is_below_cost:
                    loss_display = format_number(item.loss_amount, 2)
                    badge_text = _t("pricelist.margin_badge_below_cost", loss=loss_display)
                    margin_item = QTableWidgetItem(badge_text)
                    margin_item.setForeground(status_color(DANGER))
                else:
                    margin_str = format_number(item.margin_percent or Decimal("0.0"), 1)
                    badge_text = _t("pricelist.margin_badge_safe", margin=margin_str)
                    margin_item = QTableWidgetItem(badge_text)
                    margin_item.setForeground(status_color(SUCCESS))
            else:
                margin_item = QTableWidgetItem(_t("pricelist.cost_not_set"))
                margin_item.setForeground(Qt.GlobalColor.gray)

            self.table_preview.setItem(row, 6, margin_item)

        self.lbl_preview_header.setText(_t("pricelist.preview_title", count=len(self.current_preview_items)))
        self.btn_apply.setEnabled(len(self.current_preview_items) > 0)

    def apply_and_accept(self) -> None:
        """Confirm below-cost items if present, persist bulk adjustments, and accept dialog."""
        if not self.current_preview_items:
            return

        if self.below_cost_count > 0:
            reply = QMessageBox.warning(
                self,
                _t("pricelist.below_cost_confirm_title"),
                _t("pricelist.below_cost_confirm_msg", count=self.below_cost_count),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        rule = self.get_current_rule()
        summary = f"{rule.rule_type} {rule.value} ({rule.rounding}, {rule.scope})"
        try:
            self.price_list_service.apply_bulk_adjust(self.price_list_id, self.current_preview_items, summary)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))
