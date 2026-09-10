from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialogButtonBox,
    QPushButton,
)
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtCore import Qt
from cbpos.core.services.customer_service import CustomerService
from cbpos.i18n import _t
from cbpos.ui.widgets.table_helpers import configure_table_columns


class CustomerSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("customer_selection.title"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.customer_service = CustomerService()
        self.selected_customer = None

        self.setup_ui()
        self.load_customers()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_t("customer_selection.search_placeholder"))
        self.search_input.textChanged.connect(self.filter_customers)
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
        self.table.doubleClicked.connect(self.select_customer)
        layout.addWidget(self.table)

        # Buttons
        self.btn_select = QPushButton(_t("customer_selection.btn_select"))
        self.btn_select.setObjectName("BtnCustomerSelect")
        self.btn_select.setProperty("class", "primary")
        self.btn_select.clicked.connect(self.select_customer)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        buttons.addButton(self.btn_select, QDialogButtonBox.ButtonRole.AcceptRole)
        layout.addWidget(buttons)

        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(self.select_customer)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self).activated.connect(self.select_customer)

    def load_customers(self):
        customers = self.customer_service.get_all_customers()
        self.populate_table(customers)

    def filter_customers(self, text):
        if not text:
            self.load_customers()
            return
        customers = self.customer_service.search_customers(text)
        self.populate_table(customers)

    def populate_table(self, customers):
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

    def select_customer(self):
        row = self.table.currentRow()
        if row >= 0:
            customer_id = self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            self.selected_customer = self.customer_service.get_customer(customer_id)
            self.accept()
