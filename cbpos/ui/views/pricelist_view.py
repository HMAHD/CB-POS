"""Price list view for managing named price lists and per-item price overrides."""

from decimal import Decimal

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.price_list_service import PriceListService
from cbpos.core.services.product_service import ProductService
from cbpos.core.utils.formatters import NO_VALUE, format_number, money_header
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.dialogs.bulk_price_adjust_dialog import BulkPriceAdjustDialog
from cbpos.ui.dialogs.price_list_dialog import PriceListDialog
from cbpos.ui.dialogs.set_item_price_dialog import SetItemPriceDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import INFO, NEUTRAL, SUCCESS, status_color
from cbpos.ui.styles.style_helpers import refresh_style
from cbpos.ui.widgets.table_helpers import NUMERIC_ALIGNMENT, align_numeric_headers

# Price cells keep their raw Decimal here; the text is display-only (#557).
PRICE_ROLE = Qt.ItemDataRole.UserRole
BATCH_SIZE = 50


class PriceListView(QWidget):
    """Price list management view with a sidebar of lists and a per-product price table."""

    def __init__(self):
        """Initialize services, build the UI, and load existing price lists."""
        super().__init__()
        self.setObjectName("PriceListView")
        self.price_list_service = PriceListService()
        self.product_service = ProductService()
        self.current_list = None
        self._nav_buttons: dict[int, QPushButton] = {}
        self._all_products: list = []
        self._price_map: dict[int, Decimal] = {}
        self._displayed_products: list = []
        self._loaded_count: int = 0
        self._search_query: str = ""
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)
        self.load_lists()

    def init_ui(self):
        """Build the sidebar navigation panel and the product price table layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        root.addLayout(layout, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("PriceListSplitter")
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        # ===== LEFT SIDEBAR: Navigation Panel =====
        sidebar = QWidget()
        sidebar.setObjectName("PriceListSidebarPanel")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        sidebar_layout.setSpacing(8)

        # Title
        self.sidebar_title = QLabel()
        self.sidebar_title.setObjectName("PriceListSidebarTitle")
        sidebar_layout.addWidget(self.sidebar_title)

        # Scrollable navigation area
        scroll = QScrollArea()
        scroll.setObjectName("PriceListSidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.nav_container = QWidget()
        self.nav_container.setObjectName("PriceListNavContainer")
        self.nav_layout = QVBoxLayout(self.nav_container)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(6)
        self.nav_layout.addStretch()

        scroll.setWidget(self.nav_container)
        sidebar_layout.addWidget(scroll, 1)

        # Sidebar buttons row
        sidebar_btn_row = QHBoxLayout()
        sidebar_btn_row.setSpacing(6)

        self.btn_add = QPushButton()
        self.btn_add.setObjectName("PriceListAddBtn")
        self.btn_add.setProperty("class", "primary")
        self.btn_add.clicked.connect(self.add_price_list)
        sidebar_btn_row.addWidget(self.btn_add)

        self.btn_edit = QPushButton()
        self.btn_edit.setObjectName("PriceListEditBtn")
        self.btn_edit.clicked.connect(self.edit_price_list)
        sidebar_btn_row.addWidget(self.btn_edit)

        self.btn_delete = QPushButton()
        self.btn_delete.setObjectName("PriceListDeleteBtn")
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.clicked.connect(self.delete_price_list)
        sidebar_btn_row.addWidget(self.btn_delete)

        sidebar_layout.addLayout(sidebar_btn_row)

        splitter.addWidget(sidebar)

        # ===== RIGHT PANEL: Content =====
        content = QWidget()
        content.setObjectName("PriceListContentPanel")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        # Content stack: empty state vs data
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("PriceListContentStack")

        # Page 0: Empty state
        empty_page = QWidget()
        empty_page.setObjectName("PriceListEmptyState")
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.empty_text = QLabel()
        self.empty_text.setObjectName("PriceListEmptyText")
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_text)

        self.empty_sub = QLabel()
        self.empty_sub.setObjectName("PriceListEmptySubtext")
        self.empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_sub.setWordWrap(True)
        empty_layout.addWidget(self.empty_sub)

        self.content_stack.addWidget(empty_page)

        # Page 1: Data view
        data_page = QWidget()
        data_layout = QVBoxLayout(data_page)
        data_layout.setContentsMargins(0, 0, 0, 0)
        data_layout.setSpacing(10)

        # Header
        header = QFrame()
        header.setObjectName("PriceListHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_list_name = QLabel()
        self.lbl_list_name.setObjectName("PriceListTitle")
        header_layout.addWidget(self.lbl_list_name)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("PriceListStatusBadge")
        header_layout.addWidget(self.lbl_status)

        self.lbl_dates = QLabel("")
        self.lbl_dates.setObjectName("PriceListDates")
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_dates)

        data_layout.addWidget(header)

        # Search bar
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("PriceListSearchInput")
        self.search_input.setPlaceholderText(_t("pricelist.search_placeholder"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.addAction(Icons.get(Icons.SEARCH, "#888888"), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_input)
        data_layout.addLayout(search_row)

        # Product table
        self.table = QTableWidget()
        self.table.setObjectName("PriceListDataTable")
        self.table.setColumnCount(4)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # Prices fit their header, which now carries the currency symbol (#557)
        for col in (2, 3):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.edit_item_price)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_item_context_menu)
        self.table.verticalScrollBar().valueChanged.connect(self._on_table_scroll)
        data_layout.addWidget(self.table)

        set_price_row = QHBoxLayout()
        set_price_row.addStretch()
        self.btn_bulk_adjust = QPushButton()
        self.btn_bulk_adjust.setObjectName("BtnBulkAdjust")
        self.btn_bulk_adjust.clicked.connect(self.open_bulk_adjust_dialog)
        set_price_row.addWidget(self.btn_bulk_adjust)

        self.btn_set_item_price = QPushButton()
        self.btn_set_item_price.setObjectName("BtnSetItemPrice")
        self.btn_set_item_price.clicked.connect(self.edit_selected_item_price)
        set_price_row.addWidget(self.btn_set_item_price)

        self.btn_remove_override = QPushButton()
        self.btn_remove_override.setObjectName("BtnRemoveItemOverride")
        self.btn_remove_override.setProperty("class", "danger")
        self.btn_remove_override.clicked.connect(self.remove_selected_item_override)
        self.btn_remove_override.setEnabled(False)
        set_price_row.addWidget(self.btn_remove_override)

        data_layout.addLayout(set_price_row)

        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)

        QShortcut(QKeySequence(Qt.Key.Key_Return), self.table).activated.connect(self.edit_selected_item_price)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self.table).activated.connect(self.edit_selected_item_price)

        # Footer
        footer = QFrame()
        footer.setObjectName("PriceListFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 6, 8, 6)
        self.lbl_product_count = QLabel()
        self.lbl_product_count.setObjectName("PriceListFooterLabel")
        self.lbl_count = self.lbl_product_count
        footer_layout.addWidget(self.lbl_product_count)
        footer_layout.addStretch()

        self.hint_label = QLabel()
        self.hint_label.setObjectName("PriceListFooterHint")
        footer_layout.addWidget(self.hint_label)
        data_layout.addWidget(footer)

        self.content_stack.addWidget(data_page)
        content_layout.addWidget(self.content_stack)

        splitter.addWidget(content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 760])

        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.sidebar_title.setText(_t("pricelist.sidebar_title"))
        self.btn_add.setText(_t("pricelist.btn_add"))
        self.btn_edit.setText(_t("pricelist.btn_edit"))
        self.btn_delete.setText(_t("pricelist.btn_delete"))
        self.empty_text.setText(_t("pricelist.empty_title"))
        self.empty_sub.setText(_t("pricelist.empty_subtitle"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("pricelist.header_id"),
                _t("pricelist.header_product"),
                money_header(_t("pricelist.header_base_price")),
                money_header(_t("pricelist.header_list_price")),
            ]
        )
        align_numeric_headers(self.table, (2, 3))  # Base Price, List Price
        self.hint_label.setText(_t("pricelist.footer_hint"))
        self.btn_bulk_adjust.setText(_t("pricelist.btn_bulk_adjust"))
        self.btn_set_item_price.setText(_t("pricelist.btn_set_item_price"))
        self.btn_remove_override.setText(_t("pricelist.btn_remove_override"))
        self.search_input.setPlaceholderText(_t("pricelist.search_placeholder"))
        self._update_product_count_label()

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_price_list_status(price_list) -> tuple[str, QColor]:
        """Return (label, colour) for the list's status -- the same rule checkout uses.

        Returns:
            A tuple of (status_text, foreground_colour).
        """
        status = PriceListService.get_status(price_list)
        meaning = {"disabled": NEUTRAL, "expired": NEUTRAL, "upcoming": INFO}.get(status, SUCCESS)
        return _t(f"pricelist.status_{status}"), status_color(meaning)

    # ------------------------------------------------------------------
    # Sidebar Navigation
    # ------------------------------------------------------------------

    def load_lists(self):
        """Load all price lists into the sidebar navigation."""
        # Clear existing nav buttons
        for btn in self._nav_buttons.values():
            btn.deleteLater()
        self._nav_buttons.clear()

        # Remove stretch
        while self.nav_layout.count():
            item = self.nav_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        lists = self.price_list_service.get_all_lists()
        for pl in lists:
            status_text, status_colour = self._get_price_list_status(pl)
            btn = QPushButton(pl.name)
            btn.setObjectName("PriceListNavItem")
            btn.setIcon(Icons.get("fa5s.circle", status_colour.name()))
            btn.setIconSize(QSize(10, 10))
            btn.setToolTip(status_text)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setProperty("list_id", pl.id)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked, price_list=pl: self._on_nav_clicked(price_list))
            self.nav_layout.addWidget(btn)
            self._nav_buttons[pl.id] = btn

        self.nav_layout.addStretch()

    def _on_nav_clicked(self, price_list) -> None:
        """Handle navigation item click."""
        self.current_list = price_list
        self.lbl_list_name.setText(price_list.name)

        start = price_list.start_date.strftime("%Y-%m-%d") if price_list.start_date else _t("common.na")
        end = price_list.end_date.strftime("%Y-%m-%d") if price_list.end_date else _t("common.na")
        self.lbl_dates.setText(_t("pricelist.valid_range", start=start, end=end))

        # Update status badge
        status = PriceListService.get_status(price_list)
        status_meaning = {"disabled": "neutral", "expired": "neutral", "upcoming": "accent"}.get(status, "success")
        self.lbl_status.setText(_t(f"pricelist.status_{status}"))
        self.lbl_status.setProperty("status", status_meaning)
        refresh_style(self.lbl_status)

        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self._search_query = ""

        self.load_items()
        self.content_stack.setCurrentIndex(1)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def load_items(self):
        """Populate the product table with base prices and any list-price overrides."""
        if not self.current_list:
            return

        self._all_products = self.product_service.get_all_products()
        list_items = self.price_list_service.get_items(self.current_list.id)
        self._price_map = {item.product_id: item.price for item in list_items}

        self._apply_filter_and_reset_table()

    def _on_search_changed(self, text: str) -> None:
        self._search_query = text.strip()
        self._apply_filter_and_reset_table()

    def _apply_filter_and_reset_table(self) -> None:
        query = self._search_query.lower()
        if not query:
            self._displayed_products = list(self._all_products)
        else:
            self._displayed_products = [
                p
                for p in self._all_products
                if query in (p.display_name or "").lower()
                or query in (p.name_en or "").lower()
                or (p.barcode and query in p.barcode.lower())
            ]

        self.table.setRowCount(0)
        self._loaded_count = 0
        self._load_more_items()
        self._update_product_count_label()
        self.table.verticalScrollBar().setValue(0)

    def _load_more_items(self) -> None:
        if self._loaded_count >= len(self._displayed_products):
            return

        next_batch = self._displayed_products[self._loaded_count : self._loaded_count + BATCH_SIZE]
        for p in next_batch:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(str(p.id)))
            self.table.setItem(row, 1, QTableWidgetItem(p.display_name))
            base_item = QTableWidgetItem(format_number(p.price, 2))
            base_item.setTextAlignment(NUMERIC_ALIGNMENT)
            # Edit/context-menu read the raw Decimal, never the display text (#557)
            base_item.setData(PRICE_ROLE, p.price)
            self.table.setItem(row, 2, base_item)

            list_price = self._price_map.get(p.id)
            price_display = format_number(list_price, 2) if list_price is not None else NO_VALUE

            price_item = QTableWidgetItem(price_display)
            price_item.setTextAlignment(NUMERIC_ALIGNMENT)
            price_item.setData(PRICE_ROLE, list_price)  # None = no override
            if list_price is not None:
                price_item.setForeground(status_color(SUCCESS))

            self.table.setItem(row, 3, price_item)

        self._loaded_count += len(next_batch)
        self._update_product_count_label()
        self._on_table_selection_changed()

    def _on_table_scroll(self, value: int) -> None:
        scrollbar = self.table.verticalScrollBar()
        if scrollbar.maximum() > 0 and value >= scrollbar.maximum() - 5:
            self._load_more_items()

    def _update_product_count_label(self) -> None:
        total_all = len(self._all_products)
        total_filtered = len(self._displayed_products)
        if self._search_query:
            text = _t("pricelist.showing_count", count=self._loaded_count, total=total_filtered)
        else:
            if self._loaded_count < total_all:
                text = _t("pricelist.showing_count", count=self._loaded_count, total=total_all)
            else:
                text = _t("pricelist.product_count", count=total_all)
        self.lbl_product_count.setText(text)

    def add_price_list(self):
        """Open the create dialog and persist a new price list on accept."""
        dialog = PriceListDialog(self)
        if dialog.exec():
            name, start, end, is_active = dialog.get_data()
            try:
                self.price_list_service.create_price_list(name, start, end, is_active=is_active)
                self.load_lists()
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))

    def edit_price_list(self) -> None:
        """Rename the currently selected price list and/or edit its dates."""
        if not self.current_list:
            QMessageBox.information(
                self,
                _t("pricelist.no_selection_title"),
                _t("pricelist.no_selection_edit_msg"),
            )
            return

        list_id = self.current_list.id
        dialog = PriceListDialog(self, price_list=self.current_list)
        if not dialog.exec():
            return

        name, start, end, is_active = dialog.get_data()
        try:
            self.price_list_service.update_price_list(
                list_id, name=name, start_date=start, end_date=end, is_active=is_active
            )
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))
            return

        self.load_lists()
        updated = next((pl for pl in self.price_list_service.get_all_lists() if pl.id == list_id), None)
        if updated:
            btn = self._nav_buttons.get(list_id)
            if btn:
                btn.setChecked(True)
            self._on_nav_clicked(updated)

    def delete_price_list(self) -> None:
        """Delete the currently selected price list after confirmation."""
        if not self.current_list:
            QMessageBox.information(
                self,
                _t("pricelist.no_selection_title"),
                _t("pricelist.no_selection_msg"),
            )
            return

        reply = QMessageBox.question(
            self,
            _t("pricelist.confirm_delete_title"),
            _t("pricelist.confirm_delete_msg", name=self.current_list.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.price_list_service.delete_price_list(self.current_list.id)
                self.current_list = None
                self.content_stack.setCurrentIndex(0)
                self.load_lists()
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))

    def edit_item_price(self, index):
        """Open the price editor for the double-clicked table row."""
        self._edit_item_price_row(index.row())

    def edit_selected_item_price(self) -> None:
        """Open the price editor for the currently selected row (button/Enter key)."""
        self._edit_item_price_row(self.table.currentRow())

    def remove_selected_item_override(self) -> None:
        """Remove the list price for the currently selected row via button."""
        row = self.table.currentRow()
        if row >= 0 and self._list_price(row) is not None:
            self._remove_item_override(row)

    def _on_table_selection_changed(self) -> None:
        row = self.table.currentRow()
        has_override = (row >= 0) and (self._list_price(row) is not None)
        self.btn_remove_override.setEnabled(has_override)

    def open_bulk_adjust_dialog(self) -> None:
        """Open the bulk price adjust dialog for the current price list (#544)."""
        if not self.current_list:
            return

        selected_product_ids = []
        selected_indexes = self.table.selectionModel().selectedRows()
        for idx in selected_indexes:
            row = idx.row()
            try:
                pid = int(self.table.item(row, 0).text())
                selected_product_ids.append(pid)
            except (ValueError, AttributeError):
                continue

        dialog = BulkPriceAdjustDialog(
            price_list_id=self.current_list.id,
            price_list_name=self.current_list.name,
            selected_product_ids=selected_product_ids,
            parent=self,
        )
        if dialog.exec():
            self.load_items()

    def _show_item_context_menu(self, position) -> None:
        item = self.table.itemAt(position)
        if not item or not self.current_list:
            return

        row = item.row()
        if self._list_price(row) is None:
            return

        menu = QMenu(self)
        action_remove = menu.addAction(_t("pricelist.context_remove_override"))
        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen == action_remove:
            self._remove_item_override(row)

    def _remove_item_override(self, row: int) -> None:
        if not self.current_list:
            return

        product_id = int(self.table.item(row, 0).text())
        product_name = self.table.item(row, 1).text()

        reply = QMessageBox.question(
            self,
            _t("pricelist.confirm_remove_override_title"),
            _t("pricelist.confirm_remove_override_msg", name=product_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.price_list_service.delete_item_price(self.current_list.id, product_id)
            self.load_items()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))

    def _list_price(self, row: int) -> Decimal | None:
        """The row's price-list override as a Decimal, or None if it has none."""
        return self.table.item(row, 3).data(PRICE_ROLE)

    def _edit_item_price_row(self, row: int) -> None:
        if not self.current_list or row < 0:
            return

        product_id = int(self.table.item(row, 0).text())
        product_name = self.table.item(row, 1).text()
        base_price = self.table.item(row, 2).data(PRICE_ROLE)
        list_price = self._list_price(row)
        current_price = list_price if list_price is not None else base_price

        dialog = SetItemPriceDialog(product_name, current_price, parent=self)
        if dialog.exec():
            new_price = dialog.get_price()
            try:
                self.price_list_service.set_item_price(self.current_list.id, product_id, new_price)
                self.load_items()
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))
