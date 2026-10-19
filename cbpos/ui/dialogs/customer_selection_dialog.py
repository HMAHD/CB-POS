from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.customer_service import CustomerService
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.table_helpers import attach_table_empty_state, configure_table_columns


class CustomerSelectionDialog(QDialog):
    """Dialog for searching and selecting a customer from the customer list."""

    def __init__(self, parent=None):
        """Initialize the dialog and load the customer list."""
        super().__init__(parent)
        self.setObjectName("CustomerSelectionDialog")
        self.setWindowTitle(_t("customer_selection.title"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.customer_service = CustomerService()
        self.selected_customer = None

        # Disable parent Enter shortcuts while this dialog is open so they do not collide
        self._disabled_shortcuts: list[QShortcut] = []
        if parent is not None:
            for attr_name in ("shortcut_enter", "shortcut_num_enter"):
                shortcut = getattr(parent, attr_name, None)
                if shortcut and shortcut.isEnabled():
                    shortcut.setEnabled(False)
                    self._disabled_shortcuts.append(shortcut)

        self.setup_ui()
        self.load_customers()

    def done(self, result: int) -> None:
        """Re-enable parent shortcuts before closing."""
        for shortcut in self._disabled_shortcuts:
            shortcut.setEnabled(True)
        self._disabled_shortcuts.clear()
        super().done(result)

    def showEvent(self, event) -> None:
        """Ensure search input is focused and ready for immediate typing."""
        super().showEvent(event)
        self.search_input.setFocus()
        self.search_input.selectAll()

    def eventFilter(self, watched, event):
        """Allow arrow key navigation and Enter confirmation directly from search input."""
        if watched is self.search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                row_count = self.table.rowCount()
                if row_count > 0:
                    current = self.table.currentRow()
                    next_row = min(current + 1, row_count - 1) if current >= 0 else 0
                    self.table.selectRow(next_row)
                return True
            elif key == Qt.Key.Key_Up:
                row_count = self.table.rowCount()
                if row_count > 0:
                    current = self.table.currentRow()
                    prev_row = max(current - 1, 0) if current >= 0 else 0
                    self.table.selectRow(prev_row)
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.select_customer()
                return True
        return super().eventFilter(watched, event)

    def setup_ui(self):
        """Build the search box, results table, and select/cancel buttons."""
        layout = QVBoxLayout(self)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_t("customer_selection.search_placeholder"))
        self.search_input.textChanged.connect(self.filter_customers)
        self.search_input.returnPressed.connect(self.select_customer)
        self.search_input.installEventFilter(self)
        layout.addWidget(self.search_input)

        # Table
        self.table = QTableWidget()
        self.table.setObjectName("CustomerSelectTable")
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            [
                _t("customer_selection.header_id"),
                _t("customer_selection.header_name"),
                _t("customer_selection.header_phone"),
            ]
        )
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # ID (hidden)
                1: QHeaderView.ResizeMode.Stretch,  # Name - needs the room
                2: QHeaderView.ResizeMode.ResizeToContents,  # Phone
            },
        )
        for col in (1, 2):
            self.table.horizontalHeaderItem(col).setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        attach_table_empty_state(self.table, Icons.CUSTOMERS, "common.no_items")
        self.table.doubleClicked.connect(self.select_customer)
        layout.addWidget(self.table)

        # Buttons - symmetric 38px height and 105px min width
        footer_layout, self.btn_select, self.btn_cancel = make_dialog_footer(
            primary_key="customer_selection.btn_select",
            on_primary=self.select_customer,
            on_cancel=self.reject,
            primary_object_name="BtnDialogCustomerSelect",
        )
        self.btn_select.setMinimumHeight(38)
        self.btn_select.setMinimumWidth(105)
        self.btn_cancel.setMinimumHeight(38)
        self.btn_cancel.setMinimumWidth(105)
        layout.addLayout(footer_layout)

        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(self.select_customer)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self).activated.connect(self.select_customer)

    def load_customers(self):
        """Load all customers into the results table."""
        customers = self.customer_service.get_all_customers()
        self.populate_table(customers)

    def filter_customers(self, text):
        """Filter the results table by the search text, or reload all customers if empty."""
        if not text:
            self.load_customers()
            return
        customers = self.customer_service.search_customers(text)
        self.populate_table(customers)

    def populate_table(self, customers):
        """Fill the results table with the given list of customers."""
        self.table.setRowCount(0)
        for customer in customers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(customer.id)))

            name_item = QTableWidgetItem(customer.name)
            name_item.setData(Qt.ItemDataRole.UserRole, customer.id)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, name_item)

            phone_item = QTableWidgetItem(customer.phone or "")
            phone_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, phone_item)

        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def select_customer(self):
        """Set the selected customer from the current row and accept the dialog."""
        row = self.table.currentRow()
        if row < 0 and self.table.rowCount() > 0:
            row = 0
        if row >= 0:
            item = self.table.item(row, 1)
            if item is not None:
                customer_id = item.data(Qt.ItemDataRole.UserRole)
                self.selected_customer = self.customer_service.get_customer(customer_id)
                self.accept()
