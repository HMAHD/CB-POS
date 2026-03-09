from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from cbpos.core.services.customer_service import CustomerService
from cbpos.ui.dialogs.customer_editor import CustomerEditor


class CustomerView(QWidget):
    def __init__(self):
        super().__init__()
        self.customer_service = CustomerService()
        self.init_ui()
        self.load_customers()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Top Bar
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Name or Phone...")
        self.search_input.textChanged.connect(self.filter_customers)

        self.add_btn = QPushButton("Add Customer")
        self.add_btn.clicked.connect(self.open_add_dialog)

        top_bar.addWidget(self.search_input)
        top_bar.addWidget(self.add_btn)
        layout.addLayout(top_bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Phone", "Credit Limit", "Current Debt", "Points"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_edit_dialog)
        layout.addWidget(self.table)

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
        if not customers:
            self.table.insertRow(0)
            empty_item = QTableWidgetItem("No customers found")
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
            limit_str = "{:.2f}".format(customer.credit_limit)
            self.table.setItem(row, 3, QTableWidgetItem(limit_str))

            debt_str = "{:.2f}".format(customer.current_debt)
            debt_item = QTableWidgetItem(debt_str)
            # Highlight high debt ( > 90% of limit)
            if customer.credit_limit > 0 and customer.current_debt >= (customer.credit_limit * Decimal("0.9")):
                debt_item.setForeground(QColor("red"))
                debt_item.setToolTip("High Debt Warning!")

            self.table.setItem(row, 4, debt_item)
            self.table.setItem(row, 5, QTableWidgetItem(str(customer.loyalty_points)))

    def open_add_dialog(self):
        dialog = CustomerEditor(parent=self)
        if dialog.exec():
            self.load_customers()

    def open_edit_dialog(self, index):
        row = index.row()
        customer_id = int(self.table.item(row, 0).text())
        customer = self.customer_service.get_customer(customer_id)
        if customer:
            dialog = CustomerEditor(customer, parent=self)
            if dialog.exec():
                self.load_customers()
