from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QDialogButtonBox,
    QMessageBox,
)
from PyQt6.QtGui import QColor
from cbpos.core.services.customer_service import CustomerService


class CustomerView(QWidget):
    def __init__(self):
        super().__init__()
        self.customer_service = CustomerService()
        self.setup_ui()
        self.load_customers()

    def setup_ui(self):
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
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Phone", "Credit Limit", "Current Debt", "Points"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
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
            if customer.credit_limit > 0 and customer.current_debt >= (
                customer.credit_limit * Decimal("0.9")
            ):
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


class CustomerEditor(QDialog):
    def __init__(self, customer=None, parent=None):
        super().__init__(parent)
        self.customer = customer
        self.customer_service = CustomerService()
        self.setWindowTitle("Customer Editor" if customer else "New Customer")
        self.setMinimumWidth(400)
        self.setup_ui()
        if customer:
            self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.vat_input = QLineEdit()

        self.limit_input = QDoubleSpinBox()
        self.limit_input.setRange(0, 1000000)
        self.limit_input.setDecimals(2)

        form.addRow("Name:", self.name_input)
        form.addRow("Phone:", self.phone_input)
        form.addRow("Email:", self.email_input)
        form.addRow("VAT Number:", self.vat_input)
        form.addRow("Credit Limit:", self.limit_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_data(self):
        self.name_input.setText(self.customer.name)
        self.phone_input.setText(self.customer.phone or "")
        self.email_input.setText(self.customer.email or "")
        self.vat_input.setText(self.customer.vat_number or "")
        self.limit_input.setValue(float(self.customer.credit_limit))

    def save(self):
        data = {
            "name": self.name_input.text().strip(),
            "phone": self.phone_input.text().strip() or None,
            "email": self.email_input.text().strip() or None,
            "vat_number": self.vat_input.text().strip() or None,
            "credit_limit": Decimal(str(self.limit_input.value())),
            "is_active": True,
        }

        if not data["name"]:
            QMessageBox.warning(self, "Error", "Name is required")
            return

        try:
            if self.customer:
                self.customer_service.update_customer(self.customer.id, data)
            else:
                self.customer_service.create_customer(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
