"""Price list view for managing named price lists and per-item price overrides."""

import weakref
from datetime import datetime
from decimal import Decimal

from PyQt6.QtCore import QDate, QSize, Qt
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.dialogs.set_item_price_dialog import SetItemPriceDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.table_helpers import NUMERIC_ALIGNMENT, align_numeric_headers

# Price cells keep their raw Decimal here; the text is display-only (#557).
PRICE_ROLE = Qt.ItemDataRole.UserRole


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
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        def _unregister():
            view = self_ref()
            if view is not None:
                unregister_language_callback(view.retranslate_ui)

        self.destroyed.connect(_unregister)
        self.load_lists()

    def init_ui(self):
        """Build the sidebar navigation panel and the product price table layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        from cbpos.ui.widgets.page_header import PageHeader

        self._page_header = PageHeader(icon_name=Icons.PRICE_LIST)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(16, 12, 16, 0)
        header_row.addWidget(self._page_header)
        root.addLayout(header_row)

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
        self.btn_add.clicked.connect(self.add_price_list)
        sidebar_btn_row.addWidget(self.btn_add)

        self.btn_edit = QPushButton()
        self.btn_edit.setObjectName("PriceListEditBtn")
        self.btn_edit.clicked.connect(self.edit_price_list)
        sidebar_btn_row.addWidget(self.btn_edit)

        self.btn_delete = QPushButton()
        self.btn_delete.setObjectName("PriceListDeleteBtn")
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

        # Product table
        self.table = QTableWidget()
        self.table.setObjectName("PriceListDataTable")
        self.table.setColumnCount(4)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.edit_item_price)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_item_context_menu)
        data_layout.addWidget(self.table)

        set_price_row = QHBoxLayout()
        set_price_row.addStretch()
        self.btn_set_item_price = QPushButton()
        self.btn_set_item_price.setObjectName("BtnSetItemPrice")
        self.btn_set_item_price.clicked.connect(self.edit_selected_item_price)
        set_price_row.addWidget(self.btn_set_item_price)
        data_layout.addLayout(set_price_row)

        QShortcut(QKeySequence(Qt.Key.Key_Return), self.table).activated.connect(self.edit_selected_item_price)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self.table).activated.connect(self.edit_selected_item_price)

        # Footer
        footer = QFrame()
        footer.setObjectName("PriceListFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 6, 8, 6)
        self.lbl_product_count = QLabel()
        self.lbl_product_count.setObjectName("PriceListFooterLabel")
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
        self._page_header.set_title(_t("management.sidebar_price_lists"))
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
        self.btn_set_item_price.setText(_t("pricelist.btn_set_item_price"))

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
        colour = {"disabled": "#888888", "expired": "#888888", "upcoming": "#5599FF"}.get(status, "#39FF14")
        return _t(f"pricelist.status_{status}"), QColor(colour)

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

        start = price_list.start_date.strftime("%Y-%m-%d") if price_list.start_date else "N/A"
        end = price_list.end_date.strftime("%Y-%m-%d") if price_list.end_date else "N/A"
        self.lbl_dates.setText(_t("pricelist.valid_range", start=start, end=end))

        # Update status badge
        status_text, status_colour = self._get_price_list_status(price_list)
        self.lbl_status.setText(status_text)
        colour_name = status_colour.name()
        self.lbl_status.setStyleSheet(f"color: {colour_name}; font-weight: bold; padding: 2px 8px; border-radius: 4px;")

        self.load_items()
        self.content_stack.setCurrentIndex(1)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def load_items(self):
        """Populate the product table with base prices and any list-price overrides."""
        if not self.current_list:
            return

        products = self.product_service.get_all_products()
        list_items = self.price_list_service.get_items(self.current_list.id)
        price_map = {item.product_id: item.price for item in list_items}

        self.table.setRowCount(0)
        for p in products:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(str(p.id)))
            self.table.setItem(row, 1, QTableWidgetItem(p.name_en))
            base_item = QTableWidgetItem(format_number(p.price, 2))
            base_item.setTextAlignment(NUMERIC_ALIGNMENT)
            # Edit/context-menu read the raw Decimal, never the display text (#557)
            base_item.setData(PRICE_ROLE, p.price)
            self.table.setItem(row, 2, base_item)

            list_price = price_map.get(p.id)
            price_display = format_number(list_price, 2) if list_price is not None else NO_VALUE

            price_item = QTableWidgetItem(price_display)
            price_item.setTextAlignment(NUMERIC_ALIGNMENT)
            price_item.setData(PRICE_ROLE, list_price)  # None = no override
            if list_price is not None:
                price_item.setForeground(Qt.GlobalColor.green)

            self.table.setItem(row, 3, price_item)

        self.lbl_product_count.setText(_t("pricelist.product_count", count=len(products)))

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


class PriceListDialog(QDialog):
    """Dialog for creating or editing a price list's name and validity dates."""

    def __init__(self, parent=None, price_list=None):
        """Build the form and pre-fill fields when editing an existing price list."""
        super().__init__(parent)
        self.price_list = price_list
        self.init_ui()
        self.retranslate_ui()

        if price_list:
            self.name_input.setText(price_list.name)
            if price_list.start_date:
                self.start_date.setDate(
                    QDate(price_list.start_date.year, price_list.start_date.month, price_list.start_date.day)
                )
            if price_list.end_date:
                self.end_date.setDate(
                    QDate(price_list.end_date.year, price_list.end_date.month, price_list.end_date.day)
                )
            self.active_check.setChecked(bool(price_list.is_active))

    def init_ui(self):
        """Build the name and date-range form with Save/Cancel buttons."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.start_date = QDateEdit()
        self.start_date.setDate(QDate.currentDate())
        self.start_date.setCalendarPopup(True)

        self.end_date = QDateEdit()
        self.end_date.setDate(QDate.currentDate().addYears(1))
        self.end_date.setCalendarPopup(True)

        self.active_check = QCheckBox()
        self.active_check.setChecked(True)

        self.lbl_name = QLabel()
        self.lbl_start = QLabel()
        self.lbl_end = QLabel()
        self.lbl_active = QLabel()

        form.addRow(self.lbl_name, self.name_input)
        form.addRow(self.lbl_start, self.start_date)
        form.addRow(self.lbl_end, self.end_date)
        form.addRow(self.lbl_active, self.active_check)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        title_key = "pricelist.dialog_edit_title" if self.price_list else "pricelist.dialog_title"
        self.setWindowTitle(_t(title_key))
        self.lbl_name.setText(_t("pricelist.form_name"))
        self.lbl_start.setText(_t("pricelist.form_start_date"))
        self.lbl_end.setText(_t("pricelist.form_end_date"))
        self.lbl_active.setText(_t("pricelist.form_active"))
        self.active_check.setText(_t("pricelist.form_active_hint"))

    def validate_and_accept(self) -> None:
        """Validate form fields before accepting the dialog."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                _t("common.validation_error"),
                _t("pricelist.name_required"),
            )
            return

        start = self.start_date.date()
        end = self.end_date.date()
        if start > end:
            QMessageBox.warning(
                self,
                _t("common.validation_error"),
                _t("pricelist.start_before_end"),
            )
            return

        self.accept()

    def get_data(self):
        """Return the entered (name, start, end, is_active)."""
        start = datetime.combine(self.start_date.date().toPyDate(), datetime.min.time())
        end = datetime.combine(self.end_date.date().toPyDate(), datetime.max.time())
        return self.name_input.text().strip(), start, end, self.active_check.isChecked()
