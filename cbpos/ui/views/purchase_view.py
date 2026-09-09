import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableView,
    QPushButton,
    QLabel,
    QLineEdit,
    QFormLayout,
    QDialog,
    QMessageBox,
    QComboBox,
    QDateEdit,
    QHeaderView,
    QAbstractItemView,
    QCompleter,
    QTableWidget,
    QTableWidgetItem,
    QStackedWidget,
    QFrame,
    QInputDialog,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QDate, QStringListModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QColor, QShortcut, QKeySequence, QIntValidator

from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.services.purchase_service import PurchaseService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.supplier_payable_service import SupplierPayableService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t, register_language_callback, unregister_language_callback

logger = logging.getLogger(__name__)


class SupplierTableModel(QAbstractTableModel):
    def __init__(self, suppliers):
        super().__init__()
        self.suppliers = suppliers

    def rowCount(self, parent=None):
        return len(self.suppliers)

    def columnCount(self, parent=None):
        return 5

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            supplier = self.suppliers[index.row()]
            if index.column() == 0:
                return str(supplier.id)
            if index.column() == 1:
                return supplier.company_name
            if index.column() == 2:
                return supplier.contact_person
            if index.column() == 3:
                return supplier.phone
            if index.column() == 4:
                return supplier.tax_number
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            headers = [
                _t("purchase.supplier_header_id"),
                _t("purchase.supplier_header_company"),
                _t("purchase.supplier_header_contact"),
                _t("purchase.supplier_header_phone"),
                _t("purchase.supplier_header_tax"),
            ]
            return headers[section]
        return None


class PurchaseHistoryModel(QAbstractTableModel):
    """Table model for GRN history list."""

    def __init__(self, purchases=None):
        super().__init__()
        self.purchases = purchases or []

    def rowCount(self, parent=None):
        return len(self.purchases)

    def columnCount(self, parent=None):
        return 7

    def data(self, index, role):
        if not index.isValid():
            return None
        purchase = self.purchases[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return purchase.document_number
            if col == 1:
                return purchase.date.strftime("%Y-%m-%d %H:%M") if purchase.date else ""
            if col == 2:
                return purchase.supplier.company_name if purchase.supplier else ""
            if col == 3:
                return purchase.reference_external or ""
            if col == 4:
                return str(len(purchase.items)) if purchase.items else "0"
            if col == 5:
                return format_currency(purchase.total_cost)
            if col == 6:
                return purchase.status
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (4, 5):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            headers = [
                _t("purchase.history_header_grn"),
                _t("purchase.history_header_date"),
                _t("purchase.history_header_supplier"),
                _t("purchase.history_header_ref"),
                _t("purchase.history_header_items"),
                _t("purchase.history_header_total"),
                _t("purchase.history_header_status"),
            ]
            return headers[section]
        return None

    def get_purchase(self, row: int):
        """Get purchase object at given row."""
        if 0 <= row < len(self.purchases):
            return self.purchases[row]
        return None


class GRNDetailDialog(QDialog):
    """Read-only detail view of a completed GRN."""

    def __init__(self, purchase_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("purchase.grn_detail_title"))
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        self.init_ui(purchase_id)

    def init_ui(self, purchase_id: int) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        purchase = PurchaseService.get_purchase(purchase_id)
        if not purchase:
            layout.addWidget(QLabel(_t("purchase.purchase_not_found")))
            return

        # Header
        title = QLabel(f"{_t('purchase.grn_label')}: {purchase.document_number}")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Info row
        info_layout = QHBoxLayout()
        supplier_name = purchase.supplier.company_name if purchase.supplier else "N/A"
        info_layout.addWidget(QLabel(f"{_t('purchase.form_supplier')} {supplier_name}"))
        info_layout.addWidget(QLabel(f"{_t('purchase.form_ref')} {purchase.reference_external or 'N/A'}"))
        date_str = purchase.date.strftime("%Y-%m-%d %H:%M") if purchase.date else "N/A"
        info_layout.addWidget(QLabel(f"{_t('purchase.form_date')} {date_str}"))
        info_layout.addWidget(QLabel(f"{_t('purchase.detail_status')}: {purchase.status}"))
        info_layout.addStretch()
        layout.addLayout(info_layout)

        # Items table
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            [
                _t("purchase.detail_product"),
                _t("purchase.detail_barcode"),
                _t("purchase.detail_qty"),
                _t("purchase.detail_unit_cost"),
                _t("purchase.detail_line_total"),
            ]
        )
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for item in purchase.items:
            row = table.rowCount()
            table.insertRow(row)
            product_name = item.product.name_en if item.product else "Unknown"
            barcode = item.product.barcode if item.product else ""
            line_total = item.qty_received * item.unit_cost

            table.setItem(row, 0, QTableWidgetItem(product_name))
            table.setItem(row, 1, QTableWidgetItem(barcode))

            qty_item = QTableWidgetItem(f"{item.qty_received:.3f}")  # noqa: E231
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 2, qty_item)

            cost_item = QTableWidgetItem(format_currency(item.unit_cost))
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 3, cost_item)

            total_item = QTableWidgetItem(format_currency(line_total))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 4, total_item)

        layout.addWidget(table, 1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        total_label = QLabel(f"{_t('purchase.total_cost_label')}: {format_currency(purchase.total_cost)}")
        total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        footer.addWidget(total_label)
        layout.addLayout(footer)

        # Close button
        close_btn = QPushButton(_t("common.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class SupplierDialog(QDialog):
    def __init__(self, parent=None, supplier=None):
        super().__init__(parent)
        self.supplier = supplier
        self.init_ui()
        self.retranslate_ui()

    def init_ui(self):
        self.setObjectName("SupplierDialog")
        self.setMinimumSize(420, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.form_layout = QFormLayout()
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form_layout.setSpacing(10)

        self.company_input = QLineEdit()
        self.contact_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.tax_input = QLineEdit()
        self.details_input = QLineEdit()

        # QLineEdit + validator instead of QSpinBox -- native +/- steppers
        # break under QSS (see product_editor.py's Stock group comment).
        self.payment_terms_input = QLineEdit()
        self.payment_terms_input.setPlaceholderText("0")
        self.payment_terms_input.setValidator(QIntValidator(0, 365, self))

        if self.supplier:
            self.company_input.setText(self.supplier.company_name)
            self.contact_input.setText(self.supplier.contact_person or "")
            self.phone_input.setText(self.supplier.phone or "")
            self.tax_input.setText(self.supplier.tax_number or "")
            self.details_input.setText(self.supplier.contact_details or "")
            self.payment_terms_input.setText(str(getattr(self.supplier, "payment_terms", 0)))

        self.lbl_company = QLabel()
        self.lbl_contact = QLabel()
        self.lbl_phone = QLabel()
        self.lbl_tax = QLabel()
        self.lbl_terms = QLabel()
        self.lbl_details = QLabel()

        self.form_layout.addRow(self.lbl_company, self.company_input)
        self.form_layout.addRow(self.lbl_contact, self.contact_input)
        self.form_layout.addRow(self.lbl_phone, self.phone_input)
        self.form_layout.addRow(self.lbl_tax, self.tax_input)
        self.form_layout.addRow(self.lbl_terms, self.payment_terms_input)
        self.form_layout.addRow(self.lbl_details, self.details_input)

        layout.addLayout(self.form_layout)
        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.save_btn = QPushButton()
        self.save_btn.setObjectName("BtnSave")
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("BtnCancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(self.save_btn)
        btn_box.addWidget(self.cancel_btn)
        layout.addLayout(btn_box)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        if self.supplier:
            self.setWindowTitle(_t("purchase.edit_supplier_title"))
        else:
            self.setWindowTitle(_t("purchase.add_supplier_title"))
        self.lbl_company.setText(_t("purchase.supplier_dialog_company"))
        self.lbl_contact.setText(_t("purchase.supplier_dialog_contact"))
        self.lbl_phone.setText(_t("purchase.supplier_dialog_phone"))
        self.lbl_tax.setText(_t("purchase.supplier_dialog_tax"))
        self.lbl_terms.setText(_t("purchase.supplier_dialog_terms"))
        self.lbl_details.setText(_t("purchase.supplier_dialog_details"))
        self.save_btn.setText(_t("common.save"))
        self.cancel_btn.setText(_t("common.cancel"))

    def get_data(self):
        return {
            "company_name": self.company_input.text(),
            "contact_person": self.contact_input.text(),
            "phone": self.phone_input.text(),
            "tax_number": self.tax_input.text(),
            "contact_details": self.details_input.text(),
            "payment_terms": self._parse_payment_terms(self.payment_terms_input.text()),
        }

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


class PurchaseView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))
        self.refresh_suppliers()
        self.load_products_for_completer()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Suppliers
        self.supplier_tab = QWidget()
        self.setup_supplier_tab()
        self.tabs.addTab(self.supplier_tab, "")

        # Tab 2: New GRN
        self.grn_tab = QWidget()
        self.setup_grn_tab()
        self.tabs.addTab(self.grn_tab, "")

        # Tab 3: GRN History
        self.history_tab = QWidget()
        self.setup_history_tab()
        self.tabs.addTab(self.history_tab, "")

        # Tab 4: Payables
        self.payables_tab = QWidget()
        self.setup_payables_tab()
        self.tabs.addTab(self.payables_tab, "")

    def setup_supplier_tab(self):
        layout = QVBoxLayout(self.supplier_tab)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_add_supplier = QPushButton()
        self.btn_add_supplier.clicked.connect(self.add_supplier)
        self.btn_refresh_suppliers = QPushButton()
        self.btn_refresh_suppliers.clicked.connect(self.refresh_suppliers)
        toolbar.addWidget(self.btn_add_supplier)
        toolbar.addWidget(self.btn_refresh_suppliers)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Table
        self.supplier_table = QTableView()
        self.supplier_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.supplier_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.supplier_table)

    def setup_grn_tab(self):
        layout = QVBoxLayout(self.grn_tab)

        # Header Form
        form_layout = QHBoxLayout()

        self.supplier_combo = QComboBox()
        self.invoice_input = QLineEdit()
        self.date_input = QDateEdit(QDate.currentDate())

        self.lbl_grn_supplier = QLabel()
        self.lbl_grn_ref = QLabel()
        self.lbl_grn_date = QLabel()

        form_layout.addWidget(self.lbl_grn_supplier)
        form_layout.addWidget(self.supplier_combo)
        form_layout.addWidget(self.lbl_grn_ref)
        form_layout.addWidget(self.invoice_input)
        form_layout.addWidget(self.lbl_grn_date)
        form_layout.addWidget(self.date_input)

        layout.addLayout(form_layout)

        # Product Search
        search_layout = QHBoxLayout()
        self.product_search = QLineEdit()
        self.product_search.returnPressed.connect(self.add_product_to_grid)

        # Completer
        self.products_cache = {}
        self.completer = QCompleter()
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.product_search.setCompleter(self.completer)

        self.lbl_add_product = QLabel()
        search_layout.addWidget(self.lbl_add_product)
        search_layout.addWidget(self.product_search)
        layout.addLayout(search_layout)

        # Items Grid
        self.grn_model = QStandardItemModel(0, 5)

        self.grn_table = QTableView()
        self.grn_table.setModel(self.grn_model)
        self.grn_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.grn_table)

        # Footer
        footer_layout = QHBoxLayout()
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.btn_commit = QPushButton()
        self.btn_commit.setStyleSheet("background-color: #39FF14; color: black; font-weight: bold; padding: 10px;")
        self.btn_commit.clicked.connect(self.commit_grn)

        footer_layout.addStretch()
        footer_layout.addWidget(self.total_label)
        footer_layout.addWidget(self.btn_commit)
        layout.addLayout(footer_layout)

        # Data
        self.grn_items = []  # List of dicts

    def setup_history_tab(self) -> None:
        """Setup the GRN History tab with filters and table."""
        layout = QVBoxLayout(self.history_tab)

        # Filters bar
        filter_layout = QHBoxLayout()

        self.lbl_hist_supplier = QLabel()
        filter_layout.addWidget(self.lbl_hist_supplier)
        self.history_supplier_combo = QComboBox()
        filter_layout.addWidget(self.history_supplier_combo)

        self.lbl_hist_status = QLabel()
        filter_layout.addWidget(self.lbl_hist_status)
        self.history_status_combo = QComboBox()
        filter_layout.addWidget(self.history_status_combo)

        self.lbl_hist_from = QLabel()
        filter_layout.addWidget(self.lbl_hist_from)
        self.history_date_from = QDateEdit()
        self.history_date_from.setCalendarPopup(True)
        self.history_date_from.setDate(QDate.currentDate().addMonths(-3))
        filter_layout.addWidget(self.history_date_from)

        self.lbl_hist_to = QLabel()
        filter_layout.addWidget(self.lbl_hist_to)
        self.history_date_to = QDateEdit()
        self.history_date_to.setCalendarPopup(True)
        self.history_date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.history_date_to)

        self.btn_refresh_history = QPushButton()
        self.btn_refresh_history.setProperty("class", "primary")
        self.btn_refresh_history.clicked.connect(self.refresh_history)
        filter_layout.addWidget(self.btn_refresh_history)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Table
        self.history_model = PurchaseHistoryModel()
        self.history_table = QTableView()
        self.history_table.setModel(self.history_model)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.doubleClicked.connect(self.on_history_double_click)
        layout.addWidget(self.history_table, 1)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        # Tabs
        self.tabs.setTabText(0, _t("purchase.tab_suppliers"))
        self.tabs.setTabText(1, _t("purchase.tab_new_grn"))
        self.tabs.setTabText(2, _t("purchase.tab_grn_history"))
        self.tabs.setTabText(3, _t("purchase.tab_payables"))

        # Supplier tab
        self.btn_add_supplier.setText(_t("purchase.btn_add_supplier"))
        self.btn_refresh_suppliers.setText(_t("purchase.btn_refresh"))

        # GRN tab
        self.lbl_grn_supplier.setText(_t("purchase.form_supplier"))
        self.invoice_input.setPlaceholderText(_t("purchase.invoice_placeholder"))
        self.lbl_grn_ref.setText(_t("purchase.form_ref"))
        self.lbl_grn_date.setText(_t("purchase.form_date"))
        self.lbl_add_product.setText(_t("purchase.form_add_product"))
        self.product_search.setPlaceholderText(_t("purchase.product_search_placeholder"))
        self.grn_model.setHorizontalHeaderLabels(
            [
                _t("purchase.grn_header_id"),
                _t("purchase.grn_header_product"),
                _t("purchase.grn_header_qty"),
                _t("purchase.grn_header_cost"),
                _t("purchase.grn_header_total"),
            ]
        )
        self.btn_commit.setText(_t("purchase.btn_commit_stock"))
        self.total_label.setText(f"{_t('purchase.total_cost_label')}: 0.00")

        # History tab
        self.lbl_hist_supplier.setText(_t("purchase.form_supplier"))
        self.lbl_hist_status.setText(_t("purchase.history_status_label"))
        self.lbl_hist_from.setText(_t("purchase.from"))
        self.lbl_hist_to.setText(_t("purchase.to"))
        self.btn_refresh_history.setText(_t("purchase.btn_refresh"))

        # Repopulate status combo with translations
        current_status = self.history_status_combo.currentData()
        self.history_status_combo.clear()
        self.history_status_combo.addItem(_t("purchase.all_suppliers"), None)
        self.history_status_combo.addItem(_t("purchase.status_completed"), "COMPLETED")
        self.history_status_combo.addItem(_t("purchase.status_draft"), "DRAFT")
        self.history_status_combo.addItem(_t("purchase.status_void"), "VOID")
        if current_status:
            for i in range(self.history_status_combo.count()):
                if self.history_status_combo.itemData(i) == current_status:
                    self.history_status_combo.setCurrentIndex(i)
                    break

        # Payables tab
        self.payables_title_label.setText(_t("purchase.payables_title"))
        self.payable_search.setPlaceholderText(_t("purchase.payable_search_placeholder"))
        self.btn_payable_back.setText(_t("purchase.payables_back"))
        self.btn_open_payable_supplier.setText(_t("purchase.btn_open_payable_supplier"))
        self.btn_make_payment.setText(_t("purchase.btn_make_payment"))
        self.btn_adjust_payable.setText(_t("purchase.btn_adjust_balance"))
        self.lbl_pay_from.setText(_t("purchase.from"))
        self.lbl_pay_to.setText(_t("purchase.to"))
        self.btn_pay_all.setText(_t("purchase.all"))
        self.btn_payable_range_hint_show_all.setText(_t("purchase.all"))

        # Payable table headers
        self.payable_supplier_table.setHorizontalHeaderLabels(
            [
                _t("purchase.supplier_header_id"),
                _t("purchase.payable_header_supplier"),
                _t("purchase.supplier_header_phone"),
                _t("purchase.payable_header_payable"),
                _t("purchase.payable_header_terms"),
            ]
        )
        self.payable_ledger_table.setHorizontalHeaderLabels(
            [
                _t("purchase.ledger_header_date"),
                _t("purchase.ledger_header_type"),
                _t("purchase.ledger_header_doc"),
                _t("purchase.ledger_header_debit"),
                _t("purchase.ledger_header_credit"),
                _t("purchase.ledger_header_balance"),
            ]
        )

    def refresh_history(self) -> None:
        """Refresh the GRN history table with current filters."""
        supplier_id = self.history_supplier_combo.currentData()
        status = self.history_status_combo.currentData()

        qd_from = self.history_date_from.date()
        date_from = datetime(qd_from.year(), qd_from.month(), qd_from.day())

        qd_to = self.history_date_to.date()
        date_to = datetime(qd_to.year(), qd_to.month(), qd_to.day(), 23, 59, 59)

        purchases = PurchaseService.get_all_purchases(
            status=status,
            supplier_id=supplier_id,
            date_from=date_from,
            date_to=date_to,
        )

        self.history_model = PurchaseHistoryModel(purchases)
        self.history_table.setModel(self.history_model)

    def on_history_double_click(self, index) -> None:
        """Open GRN detail dialog on double-click."""
        purchase = self.history_model.get_purchase(index.row())
        if purchase:
            dialog = GRNDetailDialog(purchase.id, self)
            dialog.exec()

    def refresh_suppliers(self):
        self.suppliers = SupplierService.get_all_suppliers()
        self.supplier_table.setModel(SupplierTableModel(self.suppliers))

        # Update GRN Combo
        self.supplier_combo.clear()
        for s in self.suppliers:
            self.supplier_combo.addItem(s.company_name, s.id)

        # Update History Combo
        if hasattr(self, "history_supplier_combo"):
            current_data = self.history_supplier_combo.currentData()
            self.history_supplier_combo.clear()
            self.history_supplier_combo.addItem(_t("purchase.all_suppliers"), None)
            for s in self.suppliers:
                self.history_supplier_combo.addItem(s.company_name, s.id)
            # Restore selection
            if current_data:
                for i in range(self.history_supplier_combo.count()):
                    if self.history_supplier_combo.itemData(i) == current_data:
                        self.history_supplier_combo.setCurrentIndex(i)
                        break

        # Update Payables Tab
        if hasattr(self, "payable_supplier_table"):
            self.load_payable_suppliers()

    def add_supplier(self):
        dialog = SupplierDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            SupplierService.create_supplier(**data)
            self.refresh_suppliers()

    def load_products_for_completer(self):
        """Populate the Add Product completer with real product names/barcodes."""
        products = ProductService().get_all_products()
        names = []
        self.products_cache = {}
        for p in products:
            key = f"{p.name_en} [{p.barcode}]"
            names.append(key)
            self.products_cache[key] = p
            self.products_cache[p.barcode] = p

        self.completer.setModel(QStringListModel(names))

    def add_product_to_grid(self):
        query = self.product_search.text().strip()
        if not query:
            return

        product = self.products_cache.get(query)
        if not product:
            QMessageBox.warning(self, _t("purchase.not_found_title"), _t("purchase.product_not_found"))
            return

        # Add to grid
        qty = Decimal("1.000")
        cost = product.cost  # Default to current cost

        self.grn_items.append({"product": product, "qty": qty, "cost": cost})

        row = self.grn_model.rowCount()
        self.grn_model.insertRow(row)
        self.grn_model.setItem(row, 0, QStandardItem(str(product.id)))
        self.grn_model.setItem(row, 1, QStandardItem(product.name_en))
        self.grn_model.setItem(row, 2, QStandardItem(str(qty)))
        self.grn_model.setItem(row, 3, QStandardItem(str(cost)))
        self.grn_model.setItem(row, 4, QStandardItem(str(qty * cost)))

        self.product_search.clear()
        self.update_total()

    def update_total(self):
        total = sum(item["qty"] * item["cost"] for item in self.grn_items)
        total_str = format(total, ".2f")
        self.total_label.setText(f"{_t('purchase.total_cost_label')}: {total_str}")

    def set_user(self, user):
        self.user = user

    def commit_grn(self):
        supplier_id = self.supplier_combo.currentData()
        ref_no = self.invoice_input.text()

        if not supplier_id or not ref_no:
            QMessageBox.warning(
                self,
                _t("common.error"),
                _t("purchase.error_supplier_ref"),
            )
            return

        if not self.grn_items:
            QMessageBox.warning(self, _t("common.error"), _t("purchase.error_no_items"))
            return

        if not hasattr(self, "user") or not self.user:
            QMessageBox.warning(self, _t("common.error"), _t("purchase.error_no_user"))
            return

        try:
            # 1. Create Draft
            purchase = PurchaseService.create_purchase(
                supplier_id=supplier_id,
                reference_external=ref_no,
                user_id=self.user.id,
            )

            # 2. Prepare Items
            items_data = []
            for i in range(self.grn_model.rowCount()):
                # Read from table in case user edited
                prod_id = int(self.grn_model.item(i, 0).text())
                qty = Decimal(self.grn_model.item(i, 2).text())
                cost = Decimal(self.grn_model.item(i, 3).text())

                items_data.append({"product_id": prod_id, "qty": qty, "cost": cost})

            # 3. Commit
            PurchaseService.commit_purchase(purchase.id, items_data)

            QMessageBox.information(
                self,
                _t("common.success"),
                _t("purchase.grn_committed_msg", doc_number=purchase.document_number),
            )

            # Reset
            self.grn_model.removeRows(0, self.grn_model.rowCount())
            self.grn_items = []
            self.invoice_input.clear()
            self.update_total()

        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))

    # ========== Payables Tab ==========

    def setup_payables_tab(self) -> None:
        """Setup the Payables tab with drill-down navigation (no splitter)."""
        layout = QVBoxLayout(self.payables_tab)
        layout.setContentsMargins(0, 0, 0, 0)

        self.payable_stack = QStackedWidget()
        self.payable_stack.setObjectName("PayableStack")
        layout.addWidget(self.payable_stack)

        # State
        self.selected_payable_supplier = None

        # ===== PAGE 0: Supplier List =====
        self._build_payable_list_page()

        # ===== PAGE 1: Supplier Ledger Detail =====
        self._build_payable_detail_page()

    def _build_payable_list_page(self) -> None:
        """Build the supplier list page for payables."""
        page = QWidget()
        page.setObjectName("PayableListPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 16, 16, 16)
        page_layout.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        self.payables_title_label = QLabel()
        self.payables_title_label.setObjectName("PayablePageTitle")
        header_row.addWidget(self.payables_title_label)
        header_row.addStretch()
        page_layout.addLayout(header_row)

        # Search
        self.payable_search = QLineEdit()
        self.payable_search.setObjectName("PayableSearchInput")
        self.payable_search.textChanged.connect(self.filter_payable_suppliers)
        page_layout.addWidget(self.payable_search)

        # Supplier Table (full width)
        self.payable_supplier_table = QTableWidget()
        self.payable_supplier_table.setObjectName("PayableSupplierTable")
        self.payable_supplier_table.setColumnCount(5)
        self.payable_supplier_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.payable_supplier_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.payable_supplier_table.setColumnHidden(0, True)
        self.payable_supplier_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.payable_supplier_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.payable_supplier_table.setAlternatingRowColors(True)
        self.payable_supplier_table.verticalHeader().setVisible(False)
        self.payable_supplier_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.payable_supplier_table.doubleClicked.connect(self._on_payable_supplier_double_click)
        page_layout.addWidget(self.payable_supplier_table, 1)

        open_row = QHBoxLayout()
        open_row.addStretch()
        self.btn_open_payable_supplier = QPushButton()
        self.btn_open_payable_supplier.setObjectName("BtnOpenPayableSupplier")
        self.btn_open_payable_supplier.clicked.connect(self._open_selected_payable_supplier)
        open_row.addWidget(self.btn_open_payable_supplier)
        page_layout.addLayout(open_row)

        QShortcut(QKeySequence(Qt.Key.Key_Return), self.payable_supplier_table).activated.connect(
            self._open_selected_payable_supplier
        )
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self.payable_supplier_table).activated.connect(
            self._open_selected_payable_supplier
        )

        self.payable_stack.addWidget(page)

    def _build_payable_detail_page(self) -> None:
        """Build the supplier ledger detail page for payables."""
        page = QWidget()
        page.setObjectName("PayableDetailPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 16, 16, 16)
        page_layout.setSpacing(12)

        # Back button
        nav_row = QHBoxLayout()
        self.btn_payable_back = QPushButton()
        self.btn_payable_back.setObjectName("PayableBackBtn")
        self.btn_payable_back.clicked.connect(self._payable_go_back)
        nav_row.addWidget(self.btn_payable_back)
        nav_row.addStretch()
        page_layout.addLayout(nav_row)

        # Header Card
        self.payable_header = QFrame()
        self.payable_header.setObjectName("PayableHeaderCard")
        header_layout = QVBoxLayout(self.payable_header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(8)

        row1 = QHBoxLayout()
        self.lbl_pay_name = QLabel()
        self.lbl_pay_name.setObjectName("PayableCustName")
        self.lbl_pay_phone = QLabel("")
        self.lbl_pay_phone.setObjectName("PayableCustPhone")
        row1.addWidget(self.lbl_pay_name)
        row1.addStretch()
        row1.addWidget(self.lbl_pay_phone)
        header_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(16)
        self.lbl_pay_balance = QLabel()
        self.lbl_pay_balance.setObjectName("PayableMetricDebt")
        self.lbl_pay_last = QLabel()
        self.lbl_pay_last.setObjectName("PayableMetricLast")
        row2.addWidget(self.lbl_pay_balance)
        row2.addStretch()
        row2.addWidget(self.lbl_pay_last)
        header_layout.addLayout(row2)

        page_layout.addWidget(self.payable_header)

        # Action Buttons
        action_bar = QFrame()
        action_bar.setObjectName("PayableActionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)

        self.btn_make_payment = QPushButton()
        self.btn_make_payment.setObjectName("PayablePayBtn")
        self.btn_make_payment.clicked.connect(self.make_payment)
        action_layout.addWidget(self.btn_make_payment)

        self.btn_adjust_payable = QPushButton()
        self.btn_adjust_payable.setObjectName("PayableAdjustBtn")
        self.btn_adjust_payable.clicked.connect(self.adjust_payable)
        action_layout.addWidget(self.btn_adjust_payable)

        action_layout.addStretch()
        page_layout.addWidget(action_bar)

        # Date Filters
        filter_bar = QFrame()
        filter_bar.setObjectName("PayableFilterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)

        self.lbl_pay_from = QLabel()
        self.lbl_pay_from.setObjectName("PayableFilterLabel")
        filter_layout.addWidget(self.lbl_pay_from)
        self.pay_date_from = QDateEdit()
        self.pay_date_from.setObjectName("PayableDateEdit")
        self.pay_date_from.setCalendarPopup(True)
        self.pay_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.pay_date_from.dateChanged.connect(self.reload_payable_ledger)
        filter_layout.addWidget(self.pay_date_from)

        self.lbl_pay_to = QLabel()
        self.lbl_pay_to.setObjectName("PayableFilterLabel")
        filter_layout.addWidget(self.lbl_pay_to)
        self.pay_date_to = QDateEdit()
        self.pay_date_to.setObjectName("PayableDateEdit")
        self.pay_date_to.setCalendarPopup(True)
        self.pay_date_to.setDate(QDate.currentDate())
        self.pay_date_to.dateChanged.connect(self.reload_payable_ledger)
        filter_layout.addWidget(self.pay_date_to)

        self.btn_pay_all = QPushButton()
        self.btn_pay_all.setObjectName("PayableAllDatesBtn")
        self.btn_pay_all.clicked.connect(self.show_all_payable_dates)
        filter_layout.addWidget(self.btn_pay_all)
        filter_layout.addStretch()
        page_layout.addWidget(filter_bar)

        # Range-mismatch hint (#282): current_payable is an unfiltered
        # running total, but the ledger table honors the selected date
        # range -- a purchase outside that range can leave the visible
        # closing balance out of sync with the header balance above, with
        # nothing on screen explaining why. Shown only when they disagree.
        self.payable_range_hint = QFrame()
        self.payable_range_hint.setObjectName("PayableRangeHint")
        hint_layout = QHBoxLayout(self.payable_range_hint)
        hint_layout.setContentsMargins(10, 6, 10, 6)
        self.lbl_payable_range_hint = QLabel()
        self.lbl_payable_range_hint.setObjectName("PayableRangeHintLabel")
        self.lbl_payable_range_hint.setWordWrap(True)
        hint_layout.addWidget(self.lbl_payable_range_hint, 1)
        self.btn_payable_range_hint_show_all = QPushButton()
        self.btn_payable_range_hint_show_all.setObjectName("PayableRangeHintBtn")
        self.btn_payable_range_hint_show_all.clicked.connect(self.show_all_payable_dates)
        hint_layout.addWidget(self.btn_payable_range_hint_show_all)
        self.payable_range_hint.setVisible(False)
        page_layout.addWidget(self.payable_range_hint)

        # Ledger Table (full width)
        self.payable_ledger_table = QTableWidget()
        self.payable_ledger_table.setObjectName("PayableLedgerTable")
        self.payable_ledger_table.setColumnCount(6)
        self.payable_ledger_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.payable_ledger_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.payable_ledger_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.payable_ledger_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.payable_ledger_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.payable_ledger_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.payable_ledger_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.payable_ledger_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.payable_ledger_table.setAlternatingRowColors(True)
        self.payable_ledger_table.verticalHeader().setVisible(False)
        self.payable_ledger_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page_layout.addWidget(self.payable_ledger_table, 1)

        # Footer Summary
        footer = QFrame()
        footer.setObjectName("PayableLedgerFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        self.lbl_total_purchases = QLabel()
        self.lbl_total_purchases.setObjectName("PayableLedgerDebit")
        self.lbl_total_payments = QLabel()
        self.lbl_total_payments.setObjectName("PayableLedgerCredit")
        self.lbl_closing = QLabel()
        self.lbl_closing.setObjectName("PayableLedgerClosing")
        footer_layout.addWidget(self.lbl_total_purchases)
        footer_layout.addWidget(self.lbl_total_payments)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_closing)
        page_layout.addWidget(footer)

        self.payable_stack.addWidget(page)

    def load_payable_suppliers(self) -> None:
        """Load suppliers into the payables table."""
        suppliers = SupplierService.get_all_suppliers()
        self._populate_payable_table(suppliers)

    def filter_payable_suppliers(self, text: str) -> None:
        """Filter payable suppliers by search text."""
        suppliers = SupplierService.get_all_suppliers()
        if text:
            text_lower = text.lower()
            suppliers = [
                s
                for s in suppliers
                if text_lower in (s.company_name or "").lower() or text_lower in (s.phone or "").lower()
            ]
        self._populate_payable_table(suppliers)

    def _populate_payable_table(self, suppliers: list) -> None:
        """Populate the payable supplier table with color-coded status."""
        self.payable_supplier_table.setRowCount(0)
        for supplier in suppliers:
            row = self.payable_supplier_table.rowCount()
            self.payable_supplier_table.insertRow(row)

            self.payable_supplier_table.setItem(row, 0, QTableWidgetItem(str(supplier.id)))
            self.payable_supplier_table.setItem(row, 1, QTableWidgetItem(supplier.company_name))
            self.payable_supplier_table.setItem(row, 2, QTableWidgetItem(supplier.phone or ""))

            payable = getattr(supplier, "current_payable", Decimal("0.00"))
            payable_item = QTableWidgetItem(f"{payable:.2f}")  # noqa: E231
            payable_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            terms = getattr(supplier, "payment_terms", 0) or 0
            if payable == 0:
                payable_item.setForeground(QColor("#39FF14"))  # Green
            elif terms > 0:
                payable_item.setForeground(QColor("#FF851B"))  # Orange
            else:
                payable_item.setForeground(QColor("#FF4136"))  # Red

            self.payable_supplier_table.setItem(row, 3, payable_item)

            terms_item = QTableWidgetItem(f"{terms}d" if terms > 0 else "N/A")
            terms_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.payable_supplier_table.setItem(row, 4, terms_item)

    def _on_payable_supplier_double_click(self, index) -> None:
        """Drill into the selected supplier's payable ledger."""
        self._open_payable_supplier_row(index.row())

    def _open_selected_payable_supplier(self) -> None:
        """Drill into the currently selected supplier's payable ledger (button/Enter key)."""
        self._open_payable_supplier_row(self.payable_supplier_table.currentRow())

    def _open_payable_supplier_row(self, row: int) -> None:
        """Drill into the payable ledger for the given table row."""
        if row < 0:
            return
        id_item = self.payable_supplier_table.item(row, 0)
        if not id_item:
            return

        supplier_id = int(id_item.text())
        supplier = SupplierService.get_supplier_by_id(supplier_id)
        if supplier:
            self.selected_payable_supplier = supplier
            self._update_payable_header(supplier)
            self.reload_payable_ledger()
            self.payable_stack.setCurrentIndex(1)

    def _payable_go_back(self) -> None:
        """Return to the supplier list."""
        self.payable_stack.setCurrentIndex(0)
        self.load_payable_suppliers()

    def _update_payable_header(self, supplier) -> None:
        """Update the payable header card."""
        self.lbl_pay_name.setText(supplier.company_name)
        self.lbl_pay_phone.setText(supplier.phone or _t("purchase.no_phone"))

        summary = SupplierPayableService.get_supplier_summary(supplier.id)
        if summary:
            self.lbl_pay_balance.setText(
                _t("purchase.payable_label") + " " + format_currency(summary["current_payable"])
            )
            if summary["last_payment_date"]:
                self.lbl_pay_last.setText(
                    _t("purchase.last_payment_label") + " " + summary["last_payment_date"].strftime("%Y-%m-%d")
                )
            else:
                self.lbl_pay_last.setText(_t("purchase.last_payment_label") + " " + _t("purchase.none"))
        else:
            self.lbl_pay_balance.setText(_t("purchase.payable_label") + " ---")
            self.lbl_pay_last.setText(_t("purchase.last_payment_label") + " ---")

    def reload_payable_ledger(self) -> None:
        """Reload ledger entries for the selected supplier."""
        if not self.selected_payable_supplier:
            return

        date_from = datetime(
            self.pay_date_from.date().year(),
            self.pay_date_from.date().month(),
            self.pay_date_from.date().day(),
        )
        date_to = datetime(
            self.pay_date_to.date().year(),
            self.pay_date_to.date().month(),
            self.pay_date_to.date().day(),
            23,
            59,
            59,
        )

        entries = SupplierPayableService.get_ledger(
            self.selected_payable_supplier.id,
            date_from=date_from,
            date_to=date_to,
        )
        self._populate_payable_ledger(entries)

    def show_all_payable_dates(self) -> None:
        """Show all ledger entries (no date filter)."""
        if not self.selected_payable_supplier:
            return
        entries = SupplierPayableService.get_ledger(self.selected_payable_supplier.id)
        self._populate_payable_ledger(entries)

    def _populate_payable_ledger(self, entries: list) -> None:
        """Populate the payable ledger table."""
        self.payable_ledger_table.setRowCount(0)

        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        closing_balance = Decimal("0.00")

        for entry in entries:
            row = self.payable_ledger_table.rowCount()
            self.payable_ledger_table.insertRow(row)

            date_str = entry.timestamp.strftime("%Y-%m-%d %H:%M") if entry.timestamp else ""
            self.payable_ledger_table.setItem(row, 0, QTableWidgetItem(date_str))
            self.payable_ledger_table.setItem(row, 1, QTableWidgetItem(entry.entry_type))
            self.payable_ledger_table.setItem(row, 2, QTableWidgetItem(entry.reference_doc or entry.note or ""))

            if entry.amount > 0:
                # Debit (purchase increases payable)
                debit_item = QTableWidgetItem(f"{entry.amount:.2f}")  # noqa: E231
                debit_item.setForeground(QColor("#FF4136"))
                debit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.payable_ledger_table.setItem(row, 3, debit_item)
                self.payable_ledger_table.setItem(row, 4, QTableWidgetItem(""))
                total_debit += entry.amount
            else:
                # Credit (payment reduces payable)
                self.payable_ledger_table.setItem(row, 3, QTableWidgetItem(""))
                credit_item = QTableWidgetItem(f"{abs(entry.amount):.2f}")  # noqa: E231
                credit_item.setForeground(QColor("#39FF14"))
                credit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.payable_ledger_table.setItem(row, 4, credit_item)
                total_credit += abs(entry.amount)

            balance_item = QTableWidgetItem(f"{entry.balance_after:.2f}")  # noqa: E231
            balance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.payable_ledger_table.setItem(row, 5, balance_item)

            closing_balance = entry.balance_after

        self.lbl_total_purchases.setText(_t("purchase.purchases_label") + " " + format_currency(total_debit))
        self.lbl_total_payments.setText(_t("purchase.payments_label") + " " + format_currency(total_credit))
        self.lbl_closing.setText(_t("purchase.closing_label") + " " + format_currency(closing_balance))

        self._update_payable_range_hint(closing_balance)

    def _update_payable_range_hint(self, visible_closing_balance: Decimal) -> None:
        """Warn when the filtered ledger doesn't account for the supplier's
        full outstanding balance (#282)."""
        if not self.selected_payable_supplier:
            self.payable_range_hint.setVisible(False)
            return

        summary = SupplierPayableService.get_supplier_summary(self.selected_payable_supplier.id)
        actual_balance = summary["current_payable"] if summary else Decimal("0.00")

        if actual_balance != visible_closing_balance:
            self.lbl_payable_range_hint.setText(
                _t("purchase.payable_range_hint", balance=format_currency(actual_balance))
            )
            self.payable_range_hint.setVisible(True)
        else:
            self.payable_range_hint.setVisible(False)

    def make_payment(self) -> None:
        """Open supplier payment dialog."""
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.PURCHASE_MAKE_PAYMENT, self):
            return

        if not self.selected_payable_supplier:
            QMessageBox.warning(
                self,
                _t("purchase.no_supplier_title"),
                _t("purchase.no_supplier_msg"),
            )
            return

        payable = getattr(self.selected_payable_supplier, "current_payable", Decimal("0.00")) or Decimal("0.00")
        if payable <= 0:
            QMessageBox.information(
                self,
                _t("purchase.no_payable_title"),
                _t("purchase.no_payable_msg"),
            )
            return

        from cbpos.ui.dialogs.supplier_payment_dialog import SupplierPaymentDialog

        dialog = SupplierPaymentDialog(self.selected_payable_supplier.id, self)
        if dialog.exec():
            self.selected_payable_supplier = SupplierService.get_supplier_by_id(self.selected_payable_supplier.id)
            self._update_payable_header(self.selected_payable_supplier)
            self.reload_payable_ledger()
            self.load_payable_suppliers()

    def adjust_payable(self) -> None:
        """Adjust supplier payable balance."""
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.PURCHASE_ADJUST_PAYABLE, self):
            return

        if not self.selected_payable_supplier:
            QMessageBox.warning(
                self,
                _t("purchase.no_supplier_title"),
                _t("purchase.no_supplier_msg"),
            )
            return

        amount_str, ok = QInputDialog.getText(
            self,
            _t("purchase.adjust_title"),
            _t("purchase.adjust_prompt"),
        )
        if not ok or not amount_str:
            return

        try:
            amount = Decimal(amount_str)
        except (ValueError, InvalidOperation):
            QMessageBox.warning(
                self,
                _t("purchase.invalid_title"),
                _t("purchase.invalid_amount_msg"),
            )
            return

        note, ok = QInputDialog.getText(
            self,
            _t("purchase.adjust_note_title"),
            _t("purchase.adjust_note_prompt"),
        )
        if not ok or not note:
            QMessageBox.warning(
                self,
                _t("purchase.required_title"),
                _t("purchase.reason_required_msg"),
            )
            return

        current_user = AuthService.get_current_user()
        if not current_user:
            QMessageBox.warning(self, _t("common.error"), _t("purchase.error_no_user"))
            return

        try:
            SupplierPayableService.record_adjustment(
                supplier_id=self.selected_payable_supplier.id,
                amount=amount,
                note=note,
                user_id=current_user.id,
            )
            QMessageBox.information(
                self,
                _t("purchase.done_title"),
                _t("purchase.balance_adjusted_msg"),
            )
            self.selected_payable_supplier = SupplierService.get_supplier_by_id(self.selected_payable_supplier.id)
            self._update_payable_header(self.selected_payable_supplier)
            self.reload_payable_ledger()
            self.load_payable_suppliers()
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))
