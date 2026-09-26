import weakref
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.customer_service import CustomerService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.dialogs.customer_editor import CustomerEditor
from cbpos.ui.widgets.pagination_widget import PaginationWidget


class CustomerView(QWidget):
    """Paginated, searchable table of customers with add/edit access."""

    def __init__(self):
        """Build the UI and load the first page of customers."""
        super().__init__()
        self.customer_service = CustomerService()
        self._all_customers: list = []
        self.init_ui()
        self.load_customers()

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

    def init_ui(self):
        """Build the search bar, customer table, and pagination controls."""
        layout = QVBoxLayout(self)

        # Top Bar
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self.filter_customers)

        self.add_btn = QPushButton()
        self.add_btn.clicked.connect(self.open_add_dialog)

        top_bar.addWidget(self.search_input)
        top_bar.addWidget(self.add_btn)
        layout.addLayout(top_bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["", "", "", "", "", ""])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_edit_dialog)
        layout.addWidget(self.table)

        # Pagination
        self.pagination = PaginationWidget()
        self.pagination.page_changed.connect(self._on_page_changed)
        layout.addWidget(self.pagination)

    def retranslate_ui(self) -> None:
        """Update all widget text from the translation system."""
        self.search_input.setPlaceholderText(_t("customer_view.search_placeholder"))
        self.add_btn.setText(_t("customer_view.btn_add_customer"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("customer_view.header_id"),
                _t("customer_view.header_name"),
                _t("customer_view.header_phone"),
                _t("customer_view.header_credit_limit"),
                _t("customer_view.header_current_debt"),
                _t("customer_view.header_points"),
            ]
        )

    def load_customers(self):
        """Load all customers and display the current page."""
        self._all_customers = self.customer_service.get_all_customers()
        self._apply_pagination()

    def filter_customers(self, text):
        """Filter the customer list by search text, or reload all if empty."""
        if not text:
            self._all_customers = self.customer_service.get_all_customers()
        else:
            self._all_customers = self.customer_service.search_customers(text)
        self._apply_pagination()

    def _apply_pagination(self) -> None:
        self.pagination.set_total(len(self._all_customers))
        page_items = self.pagination.get_page_slice(self._all_customers)
        self._populate_table(page_items)

    def _on_page_changed(self, _page: int) -> None:
        page_items = self.pagination.get_page_slice(self._all_customers)
        self._populate_table(page_items)

    def _populate_table(self, customers):
        self.table.setRowCount(0)
        if not customers:
            self.table.insertRow(0)
            empty_item = QTableWidgetItem(_t("customer_view.empty_state"))
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(QColor("gray"))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.table.setItem(0, 0, empty_item)
            self.table.setSpan(0, 0, 1, self.table.columnCount())
            return
        for customer in customers:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(str(customer.id)))
            self.table.setItem(row, 1, QTableWidgetItem(customer.name))
            self.table.setItem(row, 2, QTableWidgetItem(customer.phone or ""))
            limit_str = f"{customer.credit_limit:.2f}"
            self.table.setItem(row, 3, QTableWidgetItem(limit_str))

            debt_str = f"{customer.current_debt:.2f}"
            debt_item = QTableWidgetItem(debt_str)
            # Highlight high debt ( > 90% of limit)
            if customer.credit_limit > 0 and customer.current_debt >= (customer.credit_limit * Decimal("0.9")):
                debt_item.setForeground(QColor("red"))
                debt_item.setToolTip(_t("customer_view.high_debt_tooltip"))

            self.table.setItem(row, 4, debt_item)
            self.table.setItem(row, 5, QTableWidgetItem(str(customer.loyalty_points)))

    def open_add_dialog(self):
        """Open the customer editor to create a new customer."""
        dialog = CustomerEditor(parent=self)
        if dialog.exec():
            self.load_customers()

    def open_edit_dialog(self, index):
        """Open the customer editor for the double-clicked row."""
        row = index.row()
        customer_id = int(self.table.item(row, 0).text())
        customer = self.customer_service.get_customer(customer_id)
        if customer:
            dialog = CustomerEditor(customer, parent=self)
            if dialog.exec():
                self.load_customers()
