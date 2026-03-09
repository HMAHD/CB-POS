from datetime import datetime
from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QInputDialog,
    QMessageBox,
    QSplitter,
    QDateEdit,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QFrame,
    QStackedWidget,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor
from cbpos.core.services.price_list_service import PriceListService
from cbpos.core.services.product_service import ProductService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback


class PriceListView(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("PriceListView")
        self.price_list_service = PriceListService()
        self.product_service = ProductService()
        self.current_list = None
        self._nav_buttons: dict[int, QPushButton] = {}
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))
        self.load_lists()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

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
        self.nav_layout.setSpacing(2)
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
        self.table.setColumnCount(5)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.edit_item_price)
        data_layout.addWidget(self.table)

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
        self.sidebar_title.setText(_t("pricelist.sidebar_title"))
        self.btn_add.setText(_t("pricelist.btn_add"))
        self.btn_delete.setText(_t("pricelist.btn_delete"))
        self.empty_text.setText(_t("pricelist.empty_title"))
        self.empty_sub.setText(_t("pricelist.empty_subtitle"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("pricelist.header_id"),
                _t("pricelist.header_product"),
                _t("pricelist.header_base_price"),
                _t("pricelist.header_list_price"),
                _t("pricelist.header_status"),
            ]
        )
        self.hint_label.setText(_t("pricelist.footer_hint"))

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_price_list_status(price_list) -> tuple[str, QColor]:
        """Return (label, colour) based on the price list dates vs today.

        Returns:
            A tuple of (status_text, foreground_colour).
        """
        today = datetime.now()
        start = price_list.start_date
        end = price_list.end_date

        if end and end < today:
            return _t("pricelist.status_expired"), QColor("#888888")
        if start and start > today:
            return _t("pricelist.status_upcoming"), QColor("#5599FF")
        return _t("pricelist.status_active"), QColor("#39FF14")

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
            status_text, _ = self._get_price_list_status(pl)
            btn = QPushButton(f"{pl.name}  [{status_text}]")
            btn.setObjectName("PriceListNavItem")
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
        self.lbl_status.setStyleSheet(
            "color: %s; font-weight: bold; padding: 2px 8px; border-radius: 4px;" % colour_name
        )

        self.load_items()
        self.content_stack.setCurrentIndex(1)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def load_items(self):
        if not self.current_list:
            return

        status_text, status_colour = self._get_price_list_status(self.current_list)
        products = self.product_service.get_all_products()
        list_items = self.price_list_service.get_items(self.current_list.id)
        price_map = {item.product_id: item.price for item in list_items}

        self.table.setRowCount(0)
        for p in products:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(str(p.id)))
            self.table.setItem(row, 1, QTableWidgetItem(p.name_en))
            self.table.setItem(row, 2, QTableWidgetItem("{:.2f}".format(p.price)))

            list_price = price_map.get(p.id)
            price_display = "{:.2f}".format(list_price) if list_price is not None else "-"

            price_item = QTableWidgetItem(price_display)
            if list_price is not None:
                price_item.setForeground(Qt.GlobalColor.green)

            self.table.setItem(row, 3, price_item)

            # Status column
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(status_colour)
            self.table.setItem(row, 4, status_item)

        self.lbl_product_count.setText(_t("pricelist.product_count", count=len(products)))

    def add_price_list(self):
        dialog = PriceListDialog(self)
        if dialog.exec():
            name, start, end = dialog.get_data()
            try:
                self.price_list_service.create_price_list(name, start, end)
                self.load_lists()
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))

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
        if not self.current_list:
            return

        row = index.row()
        product_id = int(self.table.item(row, 0).text())
        product_name = self.table.item(row, 1).text()
        base_price = Decimal(self.table.item(row, 2).text())

        current_val_str = self.table.item(row, 3).text()
        current_val = float(current_val_str) if current_val_str != "-" else float(base_price)

        new_price, ok = QInputDialog.getDouble(
            self,
            _t("pricelist.set_price_title"),
            _t("pricelist.set_price_prompt", product_name=product_name),
            value=current_val,
            min=0.01,
            decimals=2,
        )

        if ok:
            try:
                self.price_list_service.set_item_price(self.current_list.id, product_id, Decimal(str(new_price)))
                self.load_items()
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))


class PriceListDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.retranslate_ui()

    def init_ui(self):
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

        self.lbl_name = QLabel()
        self.lbl_start = QLabel()
        self.lbl_end = QLabel()

        form.addRow(self.lbl_name, self.name_input)
        form.addRow(self.lbl_start, self.start_date)
        form.addRow(self.lbl_end, self.end_date)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.setWindowTitle(_t("pricelist.dialog_title"))
        self.lbl_name.setText(_t("pricelist.form_name"))
        self.lbl_start.setText(_t("pricelist.form_start_date"))
        self.lbl_end.setText(_t("pricelist.form_end_date"))

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
        start = datetime.combine(self.start_date.date().toPyDate(), datetime.min.time())
        end = datetime.combine(self.end_date.date().toPyDate(), datetime.max.time())
        return self.name_input.text().strip(), start, end
