from decimal import Decimal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QDialogButtonBox,
    QMessageBox,
    QTabWidget,
    QWidget,
    QCheckBox,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QSpinBox,
)
from PyQt6.QtGui import QColor

from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.price_list_service import (
    PriceListService,
)  # Assuming this exists or will be needed
from cbpos.core.services.config_service import ConfigService


class CustomerEditor(QDialog):
    def __init__(self, customer=None, parent=None):
        super().__init__(parent)
        self.customer = customer
        self.customer_service = CustomerService()
        self.price_list_service = (
            PriceListService() if hasattr(self, "price_list_service") else None
        )  # Mock if not exists

        self.setWindowTitle("Customer Editor" if customer else "New Customer")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self.contacts = []  # List to hold contact dicts

        self.setup_ui()
        if customer:
            self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_general_tab(), "General")
        self.tabs.addTab(self.create_commercial_tab(), "Commercial")
        self.tabs.addTab(self.create_contacts_tab(), "Contacts")

        if ConfigService.get("enable_loyalty"):
            self.tabs.addTab(self.create_loyalty_tab(), "Loyalty")

        if self.customer:
            self.tabs.addTab(self.create_history_tab(), "History")
            self.tabs.currentChanged.connect(self.on_tab_changed)

        layout.addWidget(self.tabs)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def create_general_tab(self):
        widget = QWidget()
        form = QFormLayout(widget)

        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.address_input = QLineEdit()
        self.is_company_chk = QCheckBox("Is Company?")
        self.company_name_input = QLineEdit()

        # Toggle company name based on checkbox
        self.is_company_chk.toggled.connect(self.company_name_input.setEnabled)
        self.company_name_input.setEnabled(False)

        form.addRow("Name:", self.name_input)
        form.addRow("Phone:", self.phone_input)
        form.addRow("Email:", self.email_input)
        form.addRow("Address:", self.address_input)
        form.addRow("", self.is_company_chk)
        form.addRow("Company Name:", self.company_name_input)

        return widget

    def create_commercial_tab(self):
        widget = QWidget()
        form = QFormLayout(widget)

        self.vat_input = QLineEdit()

        self.limit_input = QDoubleSpinBox()
        self.limit_input.setRange(0, 10000000)
        self.limit_input.setDecimals(2)

        self.payment_terms_input = QSpinBox()
        self.payment_terms_input.setRange(0, 365)
        self.payment_terms_input.setSuffix(" Days")

        self.price_list_combo = QComboBox()
        self.price_list_combo.addItem("Default", None)
        # TODO: Load price lists if service exists

        form.addRow("VAT Number:", self.vat_input)
        form.addRow("Credit Limit:", self.limit_input)
        form.addRow("Payment Terms:", self.payment_terms_input)
        form.addRow("Price List:", self.price_list_combo)

        return widget

    def create_contacts_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Contact Table
        self.contact_table = QTableWidget()
        self.contact_table.setColumnCount(4)
        headers = ["Name", "Role", "Phone", "Email"]
        self.contact_table.setHorizontalHeaderLabels(headers)
        self.contact_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.contact_table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Add Contact")
        btn_remove = QPushButton("Remove Contact")

        btn_add.clicked.connect(self.add_contact_row)
        btn_remove.clicked.connect(self.remove_contact_row)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_remove)
        layout.addLayout(btn_layout)

        return widget

    def create_loyalty_tab(self):
        widget = QWidget()
        form = QFormLayout(widget)

        self.loyalty_code_input = QLineEdit()
        self.loyalty_code_input.setPlaceholderText("Scan Card Here...")

        self.points_label = QLabel("0")

        form.addRow("Loyalty Card Code:", self.loyalty_code_input)
        form.addRow("Current Points:", self.points_label)

        return widget

    def create_history_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["Date", "Receipt #", "Total", "Status", "Payment"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table)

        return widget

    def on_tab_changed(self, index):
        if self.tabs.tabText(index) == "History":
            self.load_history()

    def load_history(self):
        if not self.customer:
            return

        history = self.customer_service.get_purchase_history(self.customer.id)
        self.history_table.setRowCount(0)

        for sale in history:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            self.history_table.setItem(row, 0, QTableWidgetItem(sale.date.strftime("%Y-%m-%d %H:%M")))
            self.history_table.setItem(row, 1, QTableWidgetItem(str(sale.id)))
            self.history_table.setItem(row, 2, QTableWidgetItem("{:.2f}".format(sale.total_amount)))

            status_item = QTableWidgetItem(sale.status)
            if sale.status == "VOID":
                status_item.setForeground(QColor("red"))
            elif sale.status == "COMPLETED":  # Assuming COMPLETED is PAID equivalent
                status_item.setForeground(QColor("green"))
            self.history_table.setItem(row, 3, status_item)

            self.history_table.setItem(row, 4, QTableWidgetItem(sale.payment_method))

    def add_contact_row(self):
        row = self.contact_table.rowCount()
        self.contact_table.insertRow(row)
        self.contact_table.setItem(row, 0, QTableWidgetItem("New Contact"))
        self.contact_table.setItem(row, 1, QTableWidgetItem(""))
        self.contact_table.setItem(row, 2, QTableWidgetItem(""))
        self.contact_table.setItem(row, 3, QTableWidgetItem(""))

    def remove_contact_row(self):
        row = self.contact_table.currentRow()
        if row >= 0:
            self.contact_table.removeRow(row)

    def load_data(self):
        self.name_input.setText(self.customer.name)
        self.phone_input.setText(self.customer.phone or "")
        self.email_input.setText(self.customer.email or "")
        self.address_input.setText(self.customer.address or "")
        self.is_company_chk.setChecked(self.customer.is_company)
        self.company_name_input.setText(self.customer.company_name or "")
        self.company_name_input.setEnabled(self.customer.is_company)

        self.vat_input.setText(self.customer.vat_number or "")
        self.limit_input.setValue(float(self.customer.credit_limit))
        self.payment_terms_input.setValue(self.customer.payment_terms)

        self.loyalty_code_input.setText(self.customer.loyalty_card_code or "")
        self.points_label.setText(str(self.customer.loyalty_points))

        # Load Contacts
        if hasattr(self.customer, "contacts"):
            for contact in self.customer.contacts:
                row = self.contact_table.rowCount()
                self.contact_table.insertRow(row)
                self.contact_table.setItem(row, 0, QTableWidgetItem(contact.name))
                self.contact_table.setItem(row, 1, QTableWidgetItem(contact.role or ""))
                self.contact_table.setItem(row, 2, QTableWidgetItem(contact.phone or ""))
                self.contact_table.setItem(row, 3, QTableWidgetItem(contact.email or ""))

    def save(self):
        # Gather Contact Data
        contacts_data = []
        for row in range(self.contact_table.rowCount()):
            name_item = self.contact_table.item(row, 0)
            if not name_item or not name_item.text().strip():
                continue

            contacts_data.append(
                {
                    "name": name_item.text().strip(),
                    "role": (
                        self.contact_table.item(row, 1).text().strip() if self.contact_table.item(row, 1) else None
                    ),
                    "phone": (
                        self.contact_table.item(row, 2).text().strip() if self.contact_table.item(row, 2) else None
                    ),
                    "email": (
                        self.contact_table.item(row, 3).text().strip() if self.contact_table.item(row, 3) else None
                    ),
                }
            )

        data = {
            "name": self.name_input.text().strip(),
            "phone": self.phone_input.text().strip() or None,
            "email": self.email_input.text().strip() or None,
            "address": self.address_input.text().strip() or None,
            "is_company": self.is_company_chk.isChecked(),
            "company_name": self.company_name_input.text().strip() or None,
            "vat_number": self.vat_input.text().strip() or None,
            "credit_limit": Decimal(str(self.limit_input.value())),
            "payment_terms": self.payment_terms_input.value(),
            "loyalty_card_code": self.loyalty_code_input.text().strip() or None,
            "is_active": True,
            "contacts": contacts_data,
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
