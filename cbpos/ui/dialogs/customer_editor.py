import logging
import re
from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QDoubleValidator, QIcon, QIntValidator, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
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
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_datetime
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, INFO, NEUTRAL, SUCCESS, WARNING
from cbpos.ui.utils.layout_helpers import make_scrollable_container, protect_vertical_sizing
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.status_pill_delegate import StatusPillDelegate, set_status_pill
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    RelativeTimeTableWidgetItem,
    align_numeric_headers,
    attach_table_empty_state,
    configure_table_columns,
)
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)

COMMERCIAL_FIELD_MIN_WIDTH = 220
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_PHONE_LK = re.compile(r"^(\+94|0)\d{9}$")


def _set_button_icon(btn: QPushButton, icon_name: str, color: str, pad_right: int = 8, size: int = 14) -> None:
    """Set button icon with transparent trailing padding to ensure clear spacing before label text."""
    base_pixmap = Icons.get(icon_name, color).pixmap(size, size)
    padded = QPixmap(size + pad_right, size)
    padded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(padded)
    painter.drawPixmap(0, 0, base_pixmap)
    painter.end()
    btn.setIconSize(QSize(size + pad_right, size))
    btn.setIcon(QIcon(padded))


class CustomerEditor(QDialog):
    """Tabbed dialog for creating or editing a customer: general info, commercial terms, contacts, loyalty,
    and (when editing) purchase history."""

    def __init__(self, customer=None, parent=None):
        """Initialize the dialog, pre-filling fields when editing an existing customer."""
        super().__init__(parent)
        self.customer = customer
        self.customer_service = CustomerService()
        if customer and getattr(customer, "id", None):
            refreshed = self.customer_service.get_customer(customer.id)
            if refreshed:
                self.customer = refreshed
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
        self.tab_general = self.create_general_tab()
        self.tab_commercial = self.create_commercial_tab()
        self.tab_contacts = self.create_contacts_tab()
        self.tabs.addTab(self.tab_general, _t("customer_editor.tab_general"))
        self.tabs.addTab(self.tab_commercial, _t("customer_editor.tab_commercial"))
        self.tabs.addTab(self.tab_contacts, _t("customer_editor.tab_contacts"))

        self.tab_loyalty = self.create_loyalty_tab()
        self.tabs.addTab(self.tab_loyalty, _t("customer_editor.tab_loyalty"))
        loyalty_idx = self.tabs.indexOf(self.tab_loyalty)
        if loyalty_idx >= 0:
            self.tabs.setTabVisible(loyalty_idx, bool(ConfigService.get("enable_loyalty")))

        if self.customer:
            self.tabs.addTab(self.create_history_tab(), _t("customer_editor.tab_history"))
            self.tabs.currentChanged.connect(self.on_tab_changed)

        layout.addWidget(self.tabs)

        self._update_contacts_tab_visibility()
        self._update_tax_fields_visibility()

        # Buttons
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.save,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)
        protect_vertical_sizing(self)

    def create_general_tab(self):
        """Build the General tab: name, phone, email, address, and company toggle."""
        scroll, _widget, container_layout = make_scrollable_container(margins=(16, 16, 16, 16), spacing=12)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.address_input = QLineEdit()
        self.is_company_chk = QCheckBox(_t("customer_editor.is_company"))
        self.company_name_input = QLineEdit()

        # Toggle company name, contacts tab, and tax fields based on checkbox (#539)
        self.is_company_chk.toggled.connect(self._on_is_company_toggled)
        self.company_name_input.setEnabled(False)

        form.addRow(_t("customer_editor.name_label"), self.name_input)
        form.addRow(_t("customer_editor.phone_label"), self.phone_input)
        form.addRow(_t("customer_editor.email_label"), self.email_input)
        form.addRow(_t("customer_editor.address_label"), self.address_input)
        form.addRow("", self.is_company_chk)
        form.addRow(_t("customer_editor.company_name"), self.company_name_input)

        container_layout.addLayout(form)
        container_layout.addStretch(1)
        return scroll

    def create_commercial_tab(self):
        """Build the Commercial tab: VAT/TIN numbers, credit limit, payment terms, and price list."""
        scroll, _widget, container_layout = make_scrollable_container(margins=(16, 16, 16, 16), spacing=12)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)

        self.vat_input = QLineEdit()
        self.vat_input.setMinimumWidth(COMMERCIAL_FIELD_MIN_WIDTH)
        self._lbl_vat = QLabel(_t("customer_editor.vat_number"))

        self.tax_id_input = QLineEdit()
        self.tax_id_input.setMinimumWidth(COMMERCIAL_FIELD_MIN_WIDTH)
        self.tax_id_input.setPlaceholderText(_t("customer_editor.tin_placeholder"))
        self._lbl_tin = QLabel(_t("customer_editor.tin"))

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
        form.addRow(self._lbl_tin, self.tax_id_input)
        form.addRow(_t("customer_editor.credit_limit"), self.limit_input)
        form.addRow(_t("customer_editor.payment_terms"), self.payment_terms_input)
        form.addRow(_t("customer_editor.price_list"), self.price_list_combo)

        container_layout.addLayout(form)
        container_layout.addStretch(1)
        return scroll

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
        configure_table_columns(
            self.contact_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        attach_table_empty_state(self.contact_table, Icons.CUSTOMERS, "common.no_items")
        self.contact_table.setAlternatingRowColors(True)
        layout.addWidget(self.contact_table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_add = QPushButton(_t("customer_editor.btn_add_contact"))
        btn_add.setProperty("class", "primary")
        btn_remove = QPushButton(_t("customer_editor.btn_remove_contact"))
        btn_remove.setProperty("class", "danger")

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
        layout.setSpacing(14)

        # Overview Card
        overview_card = QFrame()
        overview_card.setObjectName("LoyaltyOverviewCard")
        overview_layout = QVBoxLayout(overview_card)
        overview_layout.setContentsMargins(16, 14, 16, 14)
        overview_layout.setSpacing(14)

        # Row 1: Loyalty Card Code input
        code_row = QHBoxLayout()
        code_row.setSpacing(10)
        lbl_code = QLabel(_t("customer_editor.loyalty_card_code"))
        lbl_code.setProperty("class", "muted")
        code_row.addWidget(lbl_code)

        self.loyalty_code_input = QLineEdit()
        self.loyalty_code_input.setPlaceholderText(_t("customer_editor.loyalty_card_placeholder"))
        self.loyalty_code_input.setObjectName("LoyaltyCodeInput")
        code_row.addWidget(self.loyalty_code_input, stretch=1)
        overview_layout.addLayout(code_row)

        # Row 2: Points Stat Strip
        points_row = QHBoxLayout()
        points_row.setSpacing(8)

        lbl_star = QLabel()
        lbl_star.setPixmap(Icons.get("fa5s.star", "#F59E0B").pixmap(24, 24))
        lbl_star.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        points_row.addWidget(lbl_star)

        self.points_label = QLabel("0")
        self.points_label.setObjectName("LoyaltyPointsValue")
        self.points_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        points_row.addWidget(self.points_label)

        points_row.addStretch()

        self.btn_adjust_points = QPushButton(_t("customer_editor.btn_adjust_points"))
        self.btn_adjust_points.setProperty("class", "secondary")
        self.btn_adjust_points.setObjectName("BtnAdjustPoints")
        _set_button_icon(self.btn_adjust_points, "fa5s.sliders-h", "#00BCEB", pad_right=8, size=13)
        has_id = bool(self.customer and getattr(self.customer, "id", None))
        self.btn_adjust_points.setEnabled(has_id)
        if not has_id:
            self.btn_adjust_points.setToolTip("Save the customer first to adjust or view loyalty history.")
        self.btn_adjust_points.clicked.connect(self.adjust_points)
        points_row.addWidget(self.btn_adjust_points)

        overview_layout.addLayout(points_row)
        layout.addWidget(overview_card)

        # Points History Header & Table
        history_header = QLabel(_t("customer_editor.points_history_title"))
        history_header.setObjectName("PointsHistoryHeader")
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
        configure_table_columns(
            self.points_history_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.Stretch,
            },
        )
        align_numeric_headers(self.points_history_table, [2, 3])
        self.points_history_table.setItemDelegateForColumn(1, StatusPillDelegate(self.points_history_table))
        attach_table_empty_state(self.points_history_table, Icons.POINTS, "common.no_items")
        layout.addWidget(self.points_history_table)

        return widget

    def adjust_points(self):
        """Prompt to adjust the customer's loyalty points with dedicated signed-mode dialog."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.ui.dialogs.adjust_points_dialog import AdjustPointsDialog

        if not check_permission_with_override(Permissions.LOYALTY_ADJUST_POINTS, self):
            return

        if not self.customer or not getattr(self.customer, "id", None):
            return

        dlg = AdjustPointsDialog(self.customer, self)
        if dlg.exec():
            if self.customer and getattr(self.customer, "id", None):
                refreshed = self.customer_service.get_customer(self.customer.id)
                if refreshed:
                    self.customer = refreshed
            pts = getattr(self.customer, "loyalty_points", 0) or 0
            if hasattr(self, "points_label"):
                self.points_label.setText(str(pts))
            self.load_points_history()

    def load_points_history(self):
        """Load points history for this customer into the points history table."""
        if not self.customer or not getattr(self.customer, "id", None) or not hasattr(self, "points_history_table"):
            return

        from cbpos.core.services.loyalty_service import LoyaltyService

        history = LoyaltyService.get_points_history(self.customer.id)
        self.points_history_table.setRowCount(0)

        if not history:
            return

        for entry in history:
            row = self.points_history_table.rowCount()
            self.points_history_table.insertRow(row)

            date_str = format_datetime(entry.timestamp) if entry.timestamp else ""
            self.points_history_table.setItem(row, 0, QTableWidgetItem(date_str))

            type_label = entry.entry_type or ""
            raw_type = (entry.entry_type or "").upper()
            if raw_type == "EARN":
                type_label = _t("customer_editor.points_type_earn")
                meaning = SUCCESS
            elif raw_type in ("REVERSAL", "REDEEM"):
                type_label = _t("customer_editor.points_type_reversal")
                meaning = WARNING
            elif raw_type == "ADJUSTMENT":
                type_label = _t("customer_editor.points_type_adjustment")
                meaning = INFO
            elif raw_type == "OPENING":
                type_label = "Opening Points"
                meaning = NEUTRAL
            else:
                meaning = NEUTRAL

            type_item = QTableWidgetItem(type_label)
            set_status_pill(type_item, type_label, meaning)
            self.points_history_table.setItem(row, 1, type_item)

            pts_str = f"+{entry.points}" if entry.points > 0 else str(entry.points)
            item_pts = QTableWidgetItem(pts_str)
            item_pts.setTextAlignment(NUMERIC_ALIGNMENT)
            self.points_history_table.setItem(row, 2, item_pts)

            item_bal = QTableWidgetItem(str(entry.balance_after))
            item_bal.setTextAlignment(NUMERIC_ALIGNMENT)
            self.points_history_table.setItem(row, 3, item_bal)

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
        configure_table_columns(
            self.history_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.Stretch,
            },
        )
        align_numeric_headers(self.history_table, [2])
        self.history_table.setItemDelegateForColumn(3, StatusPillDelegate(self.history_table))
        attach_table_empty_state(self.history_table, Icons.HISTORY, "common.no_items")
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
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

            self.history_table.setItem(row, 0, RelativeTimeTableWidgetItem(sale.date))

            self.history_table.setItem(row, 1, QTableWidgetItem(str(sale.id)))
            total_item = QTableWidgetItem(f"{sale.total_amount:.2f}")
            total_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.history_table.setItem(row, 2, total_item)

            status_item = QTableWidgetItem(sale.status)
            meaning = (
                SUCCESS if sale.status in ("COMPLETED", "PAID") else (DANGER if sale.status == "VOID" else NEUTRAL)
            )
            set_status_pill(status_item, sale.status, meaning)
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
            self._update_contacts_tab_visibility()

    def _has_contacts(self) -> bool:
        """Return True if any contact entries exist in the contacts table (#539)."""
        if not hasattr(self, "contact_table"):
            return False
        return self.contact_table.rowCount() > 0

    def _update_contacts_tab_visibility(self) -> None:
        """Show Contacts tab for company customers or if contacts already exist (#539)."""
        if not hasattr(self, "tabs") or not hasattr(self, "tab_contacts"):
            return
        contacts_idx = self.tabs.indexOf(self.tab_contacts)
        if contacts_idx >= 0:
            should_show = self.is_company_chk.isChecked() or self._has_contacts()
            self.tabs.setTabVisible(contacts_idx, should_show)
            if not should_show and self.tabs.currentIndex() == contacts_idx:
                self.tabs.setCurrentIndex(0)

    def _update_tax_fields_visibility(self) -> None:
        """Show VAT and TIN fields only for business/company customers (#539)."""
        if not hasattr(self, "is_company_chk"):
            return
        is_company = self.is_company_chk.isChecked()
        vat_active = TaxService.is_vat_active()

        show_vat = is_company and vat_active
        if hasattr(self, "_lbl_vat") and hasattr(self, "vat_input"):
            self._lbl_vat.setVisible(show_vat)
            self.vat_input.setVisible(show_vat)

        if hasattr(self, "_lbl_tin") and hasattr(self, "tax_id_input"):
            self._lbl_tin.setVisible(is_company)
            self.tax_id_input.setVisible(is_company)

    def _on_is_company_toggled(self, checked: bool) -> None:
        """Handle toggling between Individual and Business/Company customer (#539)."""
        if not checked and self._has_contacts():
            reply = QMessageBox.question(
                self,
                _t("customer_editor.confirm_drop_contacts_title"),
                _t("customer_editor.confirm_drop_contacts_message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.is_company_chk.blockSignals(True)
                self.is_company_chk.setChecked(True)
                self.is_company_chk.blockSignals(False)
                return

            self.contact_table.setRowCount(0)

        self.company_name_input.setEnabled(checked)
        self._update_contacts_tab_visibility()
        self._update_tax_fields_visibility()

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

        if hasattr(self, "loyalty_code_input"):
            self.loyalty_code_input.setText(self.customer.loyalty_card_code or "")
        pts = getattr(self.customer, "loyalty_points", 0) or 0
        if hasattr(self, "points_label"):
            self.points_label.setText(str(pts))
        if hasattr(self, "btn_adjust_points"):
            has_id = bool(self.customer and getattr(self.customer, "id", None))
            self.btn_adjust_points.setEnabled(has_id)
            if not has_id:
                self.btn_adjust_points.setToolTip("Save the customer first to adjust or view loyalty history.")
            else:
                self.btn_adjust_points.setToolTip("")
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

        self._update_contacts_tab_visibility()
        self._update_tax_fields_visibility()

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

        is_company = self.is_company_chk.isChecked()
        data = {
            "name": self.name_input.text().strip(),
            "phone": self.phone_input.text().strip() or None,
            "email": self.email_input.text().strip() or None,
            "address": self.address_input.text().strip() or None,
            "is_company": is_company,
            "company_name": (self.company_name_input.text().strip() or None) if is_company else None,
            "vat_number": (self.vat_input.text().strip() or None) if is_company else None,
            "tax_id": (self.tax_id_input.text().strip() or None) if is_company else None,
            "credit_limit": self._parse_credit_limit(self.limit_input.text()),
            "payment_terms": self._parse_payment_terms(self.payment_terms_input.text()),
            "loyalty_card_code": (
                self.loyalty_code_input.text().strip() or None
                if hasattr(self, "loyalty_code_input")
                else (getattr(self.customer, "loyalty_card_code", None) if self.customer else None)
            ),
            "is_active": True,
            "contacts": contacts_data,
        }

        if not data["name"]:
            QMessageBox.warning(self, _t("common.error"), _t("customer_editor.name_required"))
            return

        # Validate email format if provided
        if data.get("email"):
            if not _RE_EMAIL.match(data["email"]):
                QMessageBox.warning(self, _t("common.error"), _t("customer_editor.invalid_email"))
                return

        # Validate phone format if provided (Sri Lanka: +94XXXXXXXXX or 0XXXXXXXXX)
        if data.get("phone"):
            phone = data["phone"].replace(" ", "").replace("-", "")
            if not _RE_PHONE_LK.match(phone):
                QMessageBox.warning(self, _t("common.error"), _t("customer_editor.invalid_phone"))
                return

        try:
            if self.customer:
                self.customer_service.update_customer(self.customer.id, data)
            else:
                self.customer_service.create_customer(data)
            self.accept()
        except Exception as e:
            logger.exception("Failed to save customer: %s", e)
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
