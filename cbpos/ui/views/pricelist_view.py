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


class PriceListView(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("PriceListView")
        self.price_list_service = PriceListService()
        self.product_service = ProductService()
        self.current_list = None
        self._nav_buttons: dict[int, QPushButton] = {}
        self.init_ui()
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
        title = QLabel("PRICE LISTS")
        title.setObjectName("PriceListSidebarTitle")
        sidebar_layout.addWidget(title)

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

        btn_add = QPushButton("+ Add")
        btn_add.setObjectName("PriceListAddBtn")
        btn_add.clicked.connect(self.add_price_list)
        sidebar_btn_row.addWidget(btn_add)

        btn_delete = QPushButton("Delete")
        btn_delete.setObjectName("PriceListDeleteBtn")
        btn_delete.clicked.connect(self.delete_price_list)
        sidebar_btn_row.addWidget(btn_delete)

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

        empty_text = QLabel("Select a Price List")
        empty_text.setObjectName("PriceListEmptyText")
        empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_text)

        empty_sub = QLabel("Choose a price list from the sidebar to view products and prices")
        empty_sub.setObjectName("PriceListEmptySubtext")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_sub.setWordWrap(True)
        empty_layout.addWidget(empty_sub)

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

        self.lbl_list_name = QLabel("Price List Name")
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
        self.table.setHorizontalHeaderLabels(["ID", "Product", "Base Price", "List Price", "Status"])
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
        self.lbl_product_count = QLabel("0 products")
        self.lbl_product_count.setObjectName("PriceListFooterLabel")
        footer_layout.addWidget(self.lbl_product_count)
        footer_layout.addStretch()

        hint = QLabel("Double-click a row to edit its price")
        hint.setObjectName("PriceListFooterHint")
        footer_layout.addWidget(hint)
        data_layout.addWidget(footer)

        self.content_stack.addWidget(data_page)
        content_layout.addWidget(self.content_stack)

        splitter.addWidget(content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 760])

        layout.addWidget(splitter)

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
            return "Expired", QColor("#888888")
        if start and start > today:
            return "Upcoming", QColor("#5599FF")
        return "Active", QColor("#39FF14")

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
        self.lbl_dates.setText(f"Valid: {start} to {end}")

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

        self.lbl_product_count.setText(f"{len(products)} product{'s' if len(products) != 1 else ''}")

    def add_price_list(self):
        dialog = PriceListDialog(self)
        if dialog.exec():
            name, start, end = dialog.get_data()
            try:
                self.price_list_service.create_price_list(name, start, end)
                self.load_lists()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def delete_price_list(self) -> None:
        """Delete the currently selected price list after confirmation."""
        if not self.current_list:
            QMessageBox.information(self, "No Selection", "Select a price list to delete.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f'Are you sure you want to delete "{self.current_list.name}"?\n\n'
            "This will also remove all prices assigned to this list.",
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
                QMessageBox.critical(self, "Error", str(e))

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
            "Set List Price",
            f"Enter price for {product_name}: ",
            value=current_val,
            min=0.01,
            decimals=2,
        )

        if ok:
            try:
                self.price_list_service.set_item_price(self.current_list.id, product_id, Decimal(str(new_price)))
                self.load_items()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))


class PriceListDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Price List")
        self.init_ui()

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

        form.addRow("Name:", self.name_input)
        form.addRow("Start Date:", self.start_date)
        form.addRow("End Date:", self.end_date)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self) -> None:
        """Validate form fields before accepting the dialog."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Price list name is required.")
            return

        start = self.start_date.date()
        end = self.end_date.date()
        if start > end:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Start date must be on or before the end date.",
            )
            return

        self.accept()

    def get_data(self):
        start = datetime.combine(self.start_date.date().toPyDate(), datetime.min.time())
        end = datetime.combine(self.end_date.date().toPyDate(), datetime.max.time())
        return self.name_input.text().strip(), start, end
