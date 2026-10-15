from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.price_list_service import (
    PriceListService,
)  # Assuming this exists or will be needed
from cbpos.core.services.tax_service import TaxService
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

COMMERCIAL_FIELD_MIN_WIDTH = 220


class CustomerEditor(QDialog):
    """Tabbed dialog for creating or editing a customer: general info, commercial terms, contacts, loyalty,
    and (when editing) purchase history."""

    def __init__(self, customer=None, parent=None):
        """Initialize the dialog, pre-filling fields when editing an existing customer."""
        super().__init__(parent)
        self.customer = customer
        self.customer_service = CustomerService()
        self.price_list_service = (
            PriceListService() if hasattr(self, "price_list_service") else None
        )  # Mock if not exists

        self.setWindowTitle(_t("customer_editor.title_edit") if customer else _t("customer_editor.title_new"))
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.setObjectName("CustomerEditor")

        self.contacts = []  # List to hold contact dicts

        self.setup_ui()
        if customer:
            self.load_data()
        elif (default_limit := CustomerService.default_credit_limit()) > 0:
            # A new customer starts at the Settings default credit limit
            self.limit_input.setText(format(default_limit, "f"))
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def setup_ui(self):
        """Build the tab widget (General, Commercial, Contacts, optional Loyalty/History) and save/cancel buttons."""
        layout = QVBoxLayout(self)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_general_tab(), _t("customer_editor.tab_general"))
        self.tabs.addTab(self.create_commercial_tab(), _t("customer_editor.tab_commercial"))
        self.tabs.addTab(self.create_contacts_tab(), _t("customer_editor.tab_contacts"))

        if ConfigService.get("enable_loyalty"):
            self.tabs.addTab(self.create_loyalty_tab(), _t("customer_editor.tab_loyalty"))

        if self.customer:
            self.tabs.addTab(self.create_history_tab(), _t("customer_editor.tab_history"))
            self.tabs.currentChanged.connect(self.on_tab_changed)

        layout.addWidget(self.tabs)

        # Buttons
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.save,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

    def create_general_tab(self):
        """Build the General tab: name, phone, email, address, and company toggle."""
        widget = QWidget()
        form = QFormLayout(widget)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.address_input = QLineEdit()
        self.is_company_chk = QCheckBox(_t("customer_editor.is_company"))
        self.company_name_input = QLineEdit()

        # Toggle company name based on checkbox
        self.is_company_chk.toggled.connect(self.company_name_input.setEnabled)
        self.company_name_input.setEnabled(False)

        form.addRow(_t("customer_editor.name_label"), self.name_input)
        form.addRow(_t("customer_editor.phone_label"), self.phone_input)
        form.addRow(_t("customer_editor.email_label"), self.email_input)
        form.addRow(_t("customer_editor.address_label"), self.address_input)
        form.addRow("", self.is_company_chk)
        form.addRow(_t("customer_editor.company_name"), self.company_name_input)

        return widget

    def create_commercial_tab(self):
        """Build the Commercial tab: VAT/TIN numbers, credit limit, payment terms, and price list."""
        widget = QWidget()
        form = QFormLayout(widget)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.vat_input = QLineEdit()
        self.vat_input.setMinimumWidth(COMMERCIAL_FIELD_MIN_WIDTH)
        self._lbl_vat = QLabel(_t("customer_editor.vat_number"))

        self.tax_id_input = QLineEdit()
        self.tax_id_input.setMinimumWidth(COMMERCIAL_FIELD_MIN_WIDTH)
        self.tax_id_input.setPlaceholderText(_t("customer_editor.tin_placeholder"))

        # QLineEdit + validator instead of QDoubleSpinBox/QSpinBox -- native
        # +/- steppers break under QSS (see product_editor.py's Stock group).
        self.limit_input = QLineEdit()
        self.limit_input.setMinimumWidth(COMMERCIAL_FIELD_MIN_WIDTH)
        self.limit_input.setPlaceholderText("0.00")
        self.limit_input.setValidator(QDoubleValidator(0.0, 10000000.0, 2, self))

        self.payment_terms_input = QLineEdit()
        self.payment_terms_input.setMinimumWidth(COMMERCIAL_FIELD_MIN_WIDTH)
        self.payment_terms_input.setPlaceholderText("0")
        self.payment_terms_input.setValidator(QIntValidator(0, 365, self))

        self.price_list_combo = QComboBox()
        self.price_list_combo.setMinimumWidth(COMMERCIAL_FIELD_MIN_WIDTH)
        self.price_list_combo.addItem(_t("customer_editor.price_list_default"), None)
        # Price list loading deferred until PriceList management UI is complete

        form.addRow(self._lbl_vat, self.vat_input)
        # Hide VAT number field when VAT is not active
        if not TaxService.is_vat_active():
            self.vat_input.setVisible(False)
            self._lbl_vat.setVisible(False)
        form.addRow(_t("customer_editor.tin"), self.tax_id_input)
        form.addRow(_t("customer_editor.credit_limit"), self.limit_input)
        form.addRow(_t("customer_editor.payment_terms"), self.payment_terms_input)
        form.addRow(_t("customer_editor.price_list"), self.price_list_combo)

        return widget

    def create_contacts_tab(self):
        """Build the Contacts tab: an editable table of additional contact people."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Contact Table
        self.contact_table = QTableWidget()
        self.contact_table.setColumnCount(4)
        self.contact_table.setHorizontalHeaderLabels(
            [
                _t("customer_editor.contacts_header_name"),
                _t("customer_editor.contacts_header_role"),
                _t("customer_editor.contacts_header_phone"),
                _t("customer_editor.contacts_header_email"),
            ]
        )
        self.contact_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.contact_table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_add = QPushButton(_t("customer_editor.btn_add_contact"))
        btn_remove = QPushButton(_t("customer_editor.btn_remove_contact"))

        btn_add.clicked.connect(self.add_contact_row)
        btn_remove.clicked.connect(self.remove_contact_row)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_remove)
        layout.addLayout(btn_layout)

        return widget

    def create_loyalty_tab(self):
        """Build the Loyalty tab: loyalty card code, current points balance, manual adjustment and points history."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)

        self.loyalty_code_input = QLineEdit()
        self.loyalty_code_input.setPlaceholderText(_t("customer_editor.loyalty_card_placeholder"))

        points_layout = QHBoxLayout()
        self.points_label = QLabel("0")
        self.points_label.setStyleSheet("font-weight: bold;")
        points_layout.addWidget(self.points_label)

        self.btn_adjust_points = QPushButton(_t("customer_editor.btn_adjust_points"))
        self.btn_adjust_points.setEnabled(bool(self.customer and getattr(self.customer, "id", None)))
        self.btn_adjust_points.clicked.connect(self.adjust_points)
        points_layout.addSpacing(16)
        points_layout.addWidget(self.btn_adjust_points)
        points_layout.addStretch()

        form.addRow(_t("customer_editor.loyalty_card_code"), self.loyalty_code_input)
        form.addRow(_t("customer_editor.current_points"), points_layout)
        layout.addLayout(form)

        # Points History Header & Table
        history_header = QLabel(_t("customer_editor.points_history_title"))
        history_header.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(history_header)

        self.points_history_table = QTableWidget()
        self.points_history_table.setColumnCount(5)
        self.points_history_table.setHorizontalHeaderLabels(
            [
                _t("customer_editor.points_header_date"),
                _t("customer_editor.points_header_type"),
                _t("customer_editor.points_header_points"),
                _t("customer_editor.points_header_balance"),
                _t("customer_editor.points_header_reason"),
            ]
        )
        self.points_history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.points_history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.points_history_table.setAlternatingRowColors(True)
        self.points_history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.points_history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.points_history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.points_history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.points_history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.points_history_table)

        return widget

    def adjust_points(self):
        """Prompt to adjust the customer's loyalty points with permission check and required reason."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.loyalty_service import LoyaltyService
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.LOYALTY_ADJUST_POINTS, self):
            return

        if not self.customer or not getattr(self.customer, "id", None):
            return

        current_pts = getattr(self.customer, "loyalty_points", 0) or 0
        pts_delta, ok = QInputDialog.getInt(
            self,
            _t("customer_editor.adjust_points_title"),
            _t("customer_editor.adjust_points_prompt"),
            0,
            -current_pts,
            999999,
            1,
        )
        if not ok or pts_delta == 0:
            return

        reason, ok = QInputDialog.getText(
            self,
            _t("customer_editor.adjust_reason_title"),
            _t("customer_editor.adjust_reason_prompt"),
        )
        if not ok or not reason.strip():
            QMessageBox.warning(
                self,
                _t("common.error"),
                _t("customer_editor.reason_required"),
            )
            return

        current_user = AuthService.get_current_user()
        user_id = current_user.id if current_user else None

        try:
            entry = LoyaltyService.adjust_points(
                customer_id=self.customer.id,
                points_delta=pts_delta,
                reason=reason.strip(),
                user_id=user_id,
            )
            self.customer.loyalty_points = entry.balance_after
            self.points_label.setText(str(entry.balance_after))
            self.load_points_history()
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))

    def load_points_history(self):
        """Load points history for this customer into the points history table."""
        if not self.customer or not getattr(self.customer, "id", None) or not hasattr(self, "points_history_table"):
            return

        from cbpos.core.services.loyalty_service import LoyaltyService

        history = LoyaltyService.get_points_history(self.customer.id)
        self.points_history_table.setRowCount(0)

        for entry in history:
            row = self.points_history_table.rowCount()
            self.points_history_table.insertRow(row)

            date_str = entry.timestamp.strftime("%Y-%m-%d %H:%M") if entry.timestamp else ""
            self.points_history_table.setItem(row, 0, QTableWidgetItem(date_str))

            type_label = entry.entry_type or ""
            if type_label == "EARN":
                type_label = _t("customer_editor.points_type_earn")
            elif type_label == "REVERSAL":
                type_label = _t("customer_editor.points_type_reversal")
            elif type_label == "ADJUSTMENT":
                type_label = _t("customer_editor.points_type_adjustment")

            self.points_history_table.setItem(row, 1, QTableWidgetItem(type_label))

            pts_str = f"+{entry.points}" if entry.points > 0 else str(entry.points)
            self.points_history_table.setItem(row, 2, QTableWidgetItem(pts_str))
            self.points_history_table.setItem(row, 3, QTableWidgetItem(str(entry.balance_after)))

            reason_str = entry.note or ""
            if entry.reference_id:
                reason_str = f"Sale #{entry.reference_id}" + (f" - {entry.note}" if entry.note else "")
            self.points_history_table.setItem(row, 4, QTableWidgetItem(reason_str))

    def create_history_tab(self):
        """Build the History tab: a read-only table of the customer's past sales."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(
            [
                _t("customer_editor.history_header_date"),
                _t("customer_editor.history_header_receipt"),
                _t("customer_editor.history_header_total"),
                _t("customer_editor.history_header_status"),
                _t("customer_editor.history_header_payment"),
            ]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table)

        return widget

    def on_tab_changed(self, index):
        """Lazily load purchase history or points history when their tabs are opened."""
        tab_text = self.tabs.tabText(index)
        if tab_text == _t("customer_editor.tab_history"):
            self.load_history()
        elif tab_text == _t("customer_editor.tab_loyalty"):
            self.load_points_history()

    def load_history(self):
        """Load the customer's purchase history into the history table."""
        if not self.customer:
            return

        history = self.customer_service.get_purchase_history(self.customer.id)
        self.history_table.setRowCount(0)

        for sale in history:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            self.history_table.setItem(row, 0, QTableWidgetItem(sale.date.strftime("%Y-%m-%d %H:%M")))
            self.history_table.setItem(row, 1, QTableWidgetItem(str(sale.id)))
            self.history_table.setItem(row, 2, QTableWidgetItem(f"{sale.total_amount:.2f}"))

            status_item = QTableWidgetItem(sale.status)
            if sale.status == "VOID":
                status_item.setData(Qt.ItemDataRole.UserRole, "VOID")
            elif sale.status == "COMPLETED":  # Assuming COMPLETED is PAID equivalent
                status_item.setData(Qt.ItemDataRole.UserRole, "COMPLETED")
            self.history_table.setItem(row, 3, status_item)

            self.history_table.setItem(row, 4, QTableWidgetItem(sale.payment_method))

    def add_contact_row(self):
        """Append a blank editable row to the contacts table."""
        row = self.contact_table.rowCount()
        self.contact_table.insertRow(row)
        self.contact_table.setItem(row, 0, QTableWidgetItem(_t("customer_editor.new_contact")))
        self.contact_table.setItem(row, 1, QTableWidgetItem(""))
        self.contact_table.setItem(row, 2, QTableWidgetItem(""))
        self.contact_table.setItem(row, 3, QTableWidgetItem(""))

    def remove_contact_row(self):
        """Remove the currently selected row from the contacts table."""
        row = self.contact_table.currentRow()
        if row >= 0:
            self.contact_table.removeRow(row)

    def load_data(self):
        """Populate all tabs' fields from the customer being edited."""
        self.name_input.setText(self.customer.name)
        self.phone_input.setText(self.customer.phone or "")
        self.email_input.setText(self.customer.email or "")
        self.address_input.setText(self.customer.address or "")
        self.is_company_chk.setChecked(self.customer.is_company)
        self.company_name_input.setText(self.customer.company_name or "")
        self.company_name_input.setEnabled(self.customer.is_company)

        self.vat_input.setText(self.customer.vat_number or "")
        self.tax_id_input.setText(self.customer.tax_id or "")
        self.limit_input.setText(format(Decimal(self.customer.credit_limit).quantize(Decimal("0.01")), "f"))
        self.payment_terms_input.setText(str(self.customer.payment_terms))

        self.loyalty_code_input.setText(self.customer.loyalty_card_code or "")
        self.points_label.setText(str(self.customer.loyalty_points))
        if hasattr(self, "btn_adjust_points"):
            self.btn_adjust_points.setEnabled(bool(self.customer and getattr(self.customer, "id", None)))
        if hasattr(self, "points_history_table"):
            self.load_points_history()

        # Load Contacts
        if hasattr(self.customer, "contacts"):
            for contact in self.customer.contacts:
                row = self.contact_table.rowCount()
                self.contact_table.insertRow(row)
                self.contact_table.setItem(row, 0, QTableWidgetItem(contact.name))
                self.contact_table.setItem(row, 1, QTableWidgetItem(contact.role or ""))
                self.contact_table.setItem(row, 2, QTableWidgetItem(contact.phone or ""))
                self.contact_table.setItem(row, 3, QTableWidgetItem(contact.email or ""))

    @staticmethod
    def _parse_credit_limit(text: str) -> Decimal:
        """Safely parse the Credit Limit QLineEdit value to Decimal."""
        cleaned = text.strip()
        if not cleaned:
            return Decimal("0")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _parse_payment_terms(text: str) -> int:
        """Safely parse the Payment Terms QLineEdit value to int."""
        cleaned = text.strip()
        if not cleaned:
            return 0
        try:
            return int(cleaned)
        except ValueError:
            return 0

    def save(self):
        """Validate all fields and create or update the customer via CustomerService."""
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
            "tax_id": self.tax_id_input.text().strip() or None,
            "credit_limit": self._parse_credit_limit(self.limit_input.text()),
            "payment_terms": self._parse_payment_terms(self.payment_terms_input.text()),
            "loyalty_card_code": self.loyalty_code_input.text().strip() or None,
            "is_active": True,
            "contacts": contacts_data,
        }

        if not data["name"]:
            QMessageBox.warning(self, _t("common.error"), _t("customer_editor.name_required"))
            return

        # Validate email format if provided
        if data.get("email"):
            import re

            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", data["email"]):
                QMessageBox.warning(self, _t("common.error"), _t("customer_editor.invalid_email"))
                return

        # Validate phone format if provided (Sri Lanka: +94XXXXXXXXX or 0XXXXXXXXX)
        if data.get("phone"):
            import re

            phone = data["phone"].replace(" ", "").replace("-", "")
            if not re.match(r"^(\+94|0)\d{9}$", phone):
                QMessageBox.warning(self, _t("common.error"), _t("customer_editor.invalid_phone"))
                return

        try:
            if self.customer:
                self.customer_service.update_customer(self.customer.id, data)
            else:
                self.customer_service.create_customer(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))
