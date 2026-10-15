"""Purchases view: supplier management, GRN intake, purchase history, and payables."""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QAbstractTableModel, QDate, QStringListModel, Qt
from PyQt6.QtGui import QColor, QKeySequence, QShortcut, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.purchase_order_service import PurchaseOrderService
from cbpos.core.services.purchase_service import PurchaseService
from cbpos.core.services.supplier_payable_service import SupplierPayableService
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.utils.formatters import format_currency, format_quantity
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.constants import BAR_GROUP_SPACING, BAR_ITEM_SPACING, BAR_MARGIN_V
from cbpos.ui.dialogs.grn_detail_dialog import GRNDetailDialog
from cbpos.ui.dialogs.supplier_dialog import SupplierDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, SUCCESS, WARNING, status_color
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget

logger = logging.getLogger(__name__)

_DISCREPANCY_LINE_KEYS = {
    "over": "purchase.discrepancy_line",
    "under": "purchase.discrepancy_line",
    "not_on_order": "purchase.discrepancy_line_not_on_order",
    "not_received": "purchase.discrepancy_line_not_received",
}


def format_discrepancy_line(discrepancy: dict) -> str:
    """Render one PO-vs-GRN discrepancy as a translated line for the confirmation.

    Args:
        discrepancy: An entry from ``PurchaseOrderService.check_receipt_discrepancies``.

    Returns:
        The line for its ``kind``, quantities shown in the product's unit
        (``20`` for pieces, ``1.250`` for kg).
    """
    places = discrepancy.get("decimal_places")
    key = _DISCREPANCY_LINE_KEYS.get(discrepancy.get("kind", ""), "purchase.discrepancy_line")
    return _t(
        key,
        product=discrepancy["product_name"],
        outstanding=format_quantity(discrepancy["outstanding"], places),
        received=format_quantity(discrepancy["received"], places),
    )


class SupplierTableModel(QAbstractTableModel):
    """Table model for the supplier list table."""

    def __init__(self, suppliers):
        """Store the suppliers to display."""
        super().__init__()
        self.suppliers = suppliers

    def rowCount(self, parent=None):
        """Return the number of suppliers."""
        return len(self.suppliers)

    def columnCount(self, parent=None):
        """Return the fixed column count (5)."""
        return 5

    def data(self, index, role):
        """Return display text for the given supplier cell."""
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
        """Return translated column header labels."""
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
        """Store the purchases to display, defaulting to an empty list."""
        super().__init__()
        self.purchases = purchases or []

    def rowCount(self, parent=None):
        """Return the number of purchases."""
        return len(self.purchases)

    def columnCount(self, parent=None):
        """Return the fixed column count (7)."""
        return 7

    def data(self, index, role):
        """Return display text and column alignment for the given purchase cell."""
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
        """Return translated column header labels."""
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


class PurchaseView(QWidget):
    """Purchases view with Suppliers, New GRN, GRN History, and Payables tabs."""

    def __init__(self):
        """Build the UI, wire the language callback, and load initial supplier and product data."""
        super().__init__()
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)
        self.refresh_suppliers()
        self.load_products_for_completer()

    def init_ui(self):
        """Build the page header and the four purchase tabs."""
        layout = QVBoxLayout(self)

        from cbpos.ui.resources.icons import Icons
        from cbpos.ui.widgets.page_header import PageHeader

        self._page_header = PageHeader(icon_name=Icons.PURCHASE)
        layout.addWidget(self._page_header)

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
        """Build the Suppliers tab: toolbar and supplier table."""
        layout = QVBoxLayout(self.supplier_tab)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_add_supplier = QPushButton()
        self.btn_add_supplier.clicked.connect(self.add_supplier)
        self.btn_edit_supplier = QPushButton()
        self.btn_edit_supplier.clicked.connect(self.edit_supplier)
        self.btn_deactivate_supplier = QPushButton()
        self.btn_deactivate_supplier.clicked.connect(self.deactivate_supplier)
        self.btn_refresh_suppliers = QPushButton()
        self.btn_refresh_suppliers.clicked.connect(self.refresh_suppliers)
        toolbar.addWidget(self.btn_add_supplier)
        toolbar.addWidget(self.btn_edit_supplier)
        toolbar.addWidget(self.btn_deactivate_supplier)
        toolbar.addWidget(self.btn_refresh_suppliers)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Table
        self.supplier_table = QTableView()
        self.supplier_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.supplier_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.supplier_table.doubleClicked.connect(self.edit_supplier)
        layout.addWidget(self.supplier_table)

        self.empty_supplier_label = EmptyStateWidget(Icons.CUSTOMERS, self.supplier_table.viewport())
        self.empty_supplier_label.setVisible(False)

    def setup_grn_tab(self):
        """Build the New GRN tab: header form, product search, line items grid, and commit footer."""
        layout = QVBoxLayout(self.grn_tab)

        # Header Form
        self.grn_form_layout = form_layout = QHBoxLayout()

        self.supplier_combo = QComboBox()
        # Searchable -- type to filter (#280), same recipe already proven
        # for payment_dialog.py's customer combo. The QCompleter itself is
        # (re)built in refresh_suppliers() where the current supplier list
        # is available.
        self.supplier_combo.setEditable(True)
        self.supplier_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.invoice_input = QLineEdit()
        self.date_input = QDateEdit(QDate.currentDate())

        self.lbl_grn_supplier = QLabel()
        self.lbl_grn_ref = QLabel()
        self.lbl_grn_date = QLabel()

        form_layout.addWidget(self.lbl_grn_supplier)
        form_layout.addWidget(self.supplier_combo, 2)
        form_layout.addWidget(self.lbl_grn_ref)
        form_layout.addWidget(self.invoice_input, 2)
        form_layout.addWidget(self.lbl_grn_date)
        form_layout.addWidget(self.date_input, 1)

        layout.addLayout(form_layout)

        # Open Purchase Orders — receive against an existing order (#486),
        # possibly partially, possibly across more than one GRN over time.
        po_layout = QHBoxLayout()
        self.lbl_open_po = QLabel()
        self.open_po_combo = QComboBox()
        self.btn_load_po = QPushButton()
        self.btn_load_po.clicked.connect(self.load_selected_purchase_order)
        po_layout.addWidget(self.lbl_open_po)
        po_layout.addWidget(self.open_po_combo, 2)
        po_layout.addWidget(self.btn_load_po)
        layout.addLayout(po_layout)

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

        self.empty_grn_label = EmptyStateWidget(Icons.INVENTORY, self.grn_table.viewport())
        self.empty_grn_label.setVisible(True)

        def _update_grn_empty(*_):
            self.empty_grn_label.setVisible(self.grn_model.rowCount() == 0)

        self.grn_model.rowsInserted.connect(_update_grn_empty)
        self.grn_model.rowsRemoved.connect(_update_grn_empty)
        self.grn_model.modelReset.connect(_update_grn_empty)

        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, BAR_MARGIN_V, 0, BAR_MARGIN_V)
        footer_layout.setSpacing(BAR_ITEM_SPACING)

        self.lbl_grn_input_vat = QLabel()
        self.input_vat_field = QLineEdit()
        self.input_vat_field.setPlaceholderText("0.00")
        self.input_vat_field.setFixedWidth(100)
        self.input_vat_field.setToolTip(_t("purchase.input_vat_tooltip"))

        self.total_label = QLabel()
        self.total_label.setObjectName("GrnTotalLabel")

        self.btn_commit = QPushButton()
        self.btn_commit.setObjectName("BtnCommitGrn")
        self.btn_commit.setProperty("class", "primary")
        self.btn_commit.clicked.connect(self.commit_grn)

        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_grn_input_vat)
        footer_layout.addWidget(self.input_vat_field)
        footer_layout.addSpacing(BAR_GROUP_SPACING)
        footer_layout.addWidget(self.total_label)
        footer_layout.addWidget(self.btn_commit)
        layout.addLayout(footer_layout)

        # Data
        self.grn_items = []  # List of dicts
        self.current_purchase_order_id = None

    def setup_history_tab(self) -> None:
        """Setup the GRN History tab with filters and table."""
        layout = QVBoxLayout(self.history_tab)

        # Filters bar
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, BAR_MARGIN_V, 0, BAR_MARGIN_V)
        filter_layout.setSpacing(BAR_ITEM_SPACING)

        self.lbl_hist_supplier = QLabel()
        filter_layout.addWidget(self.lbl_hist_supplier)
        self.history_supplier_combo = QComboBox()
        self.history_supplier_combo.setEditable(True)
        self.history_supplier_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        filter_layout.addWidget(self.history_supplier_combo)

        self.lbl_hist_status = QLabel()
        filter_layout.addWidget(self.lbl_hist_status)
        self.history_status_combo = QComboBox()
        filter_layout.addWidget(self.history_status_combo)

        filter_layout.addSpacing(BAR_GROUP_SPACING)

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

        filter_layout.addSpacing(BAR_GROUP_SPACING)

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

        # QTableView + model has no built-in empty-row mechanism the way
        # a plain QTableWidget does, so this mirrors sales_view.py's
        # empty_cart_label: an overlay positioned over the viewport,
        # shown/hidden by refresh_history() based on whether there are
        # any rows.
        self.empty_history_label = EmptyStateWidget(Icons.PURCHASE, self.history_table.viewport())
        self.empty_history_label.setVisible(False)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self._page_header.set_title(_t("management.sidebar_purchasing"))
        # Tabs
        self.tabs.setTabText(0, _t("purchase.tab_suppliers"))
        self.tabs.setTabText(1, _t("purchase.tab_new_grn"))
        self.tabs.setTabText(2, _t("purchase.tab_grn_history"))
        self.tabs.setTabText(3, _t("purchase.tab_payables"))
        self.empty_history_label.set_title(_t("purchase.grn_history_empty_state"))
        self.empty_history_label.set_subtitle(_t("purchase.empty_history_subtitle"))
        self.empty_supplier_label.set_title(_t("purchase.empty_suppliers_title"))
        self.empty_supplier_label.set_subtitle(_t("purchase.empty_suppliers_subtitle"))
        self.empty_grn_label.set_title(_t("purchase.empty_grn_items_title"))
        self.empty_grn_label.set_subtitle(_t("purchase.empty_grn_items_subtitle"))

        # Supplier tab
        self.btn_add_supplier.setText(_t("purchase.btn_add_supplier"))
        self.btn_edit_supplier.setText(_t("purchase.btn_edit_supplier"))
        self.btn_deactivate_supplier.setText(_t("purchase.btn_deactivate_supplier"))
        self.btn_refresh_suppliers.setText(_t("purchase.btn_refresh"))

        # GRN tab
        self.lbl_grn_supplier.setText(_t("purchase.form_supplier"))
        self.invoice_input.setPlaceholderText(_t("purchase.invoice_placeholder"))
        self.lbl_grn_ref.setText(_t("purchase.form_ref"))
        self.lbl_grn_date.setText(_t("purchase.form_date"))
        self.lbl_open_po.setText(_t("purchase.open_po_label"))
        self.btn_load_po.setText(_t("purchase.btn_load_po"))
        self.refresh_open_orders()
        self.lbl_add_product.setText(_t("purchase.form_add_product"))
        self.lbl_grn_input_vat.setText(_t("purchase.grn_input_vat_label"))
        self.input_vat_field.setToolTip(_t("purchase.input_vat_tooltip"))
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
        self.history_status_combo.addItem(_t("purchase.all_statuses"), None)
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
        self.empty_history_label.setVisible(not purchases)
        if not purchases:
            self._position_empty_history_label()

    def _position_empty_history_label(self) -> None:
        """Center the empty-history hint over the table's row area (its viewport)."""
        viewport = self.history_table.viewport()
        self.empty_history_label.resize(viewport.size())

    def on_history_double_click(self, index) -> None:
        """Open GRN detail dialog on double-click."""
        purchase = self.history_model.get_purchase(index.row())
        if purchase:
            dialog = GRNDetailDialog(purchase.id, self)
            dialog.exec()

    def refresh_suppliers(self):
        """Reload suppliers and refresh the supplier table, GRN combo, history filter combo, and payables list."""
        self.suppliers = SupplierService.get_all_suppliers()
        self.supplier_table.setModel(SupplierTableModel(self.suppliers))
        if hasattr(self, "empty_supplier_label"):
            self.empty_supplier_label.setVisible(not self.suppliers)
        names = [s.company_name for s in self.suppliers]

        # Update GRN Combo
        self.supplier_combo.clear()
        for s in self.suppliers:
            self.supplier_combo.addItem(s.company_name, s.id)
        self.supplier_combo.lineEdit().setPlaceholderText(_t("purchase.search_supplier_placeholder"))
        supplier_completer = QCompleter(names, self)
        supplier_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        supplier_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.supplier_combo.setCompleter(supplier_completer)

        # Update History Combo
        if hasattr(self, "history_supplier_combo"):
            current_data = self.history_supplier_combo.currentData()
            self.history_supplier_combo.clear()
            self.history_supplier_combo.addItem(_t("purchase.all_suppliers"), None)
            for s in self.suppliers:
                self.history_supplier_combo.addItem(s.company_name, s.id)
            self.history_supplier_combo.lineEdit().setPlaceholderText(_t("purchase.search_supplier_placeholder"))
            history_completer = QCompleter([_t("purchase.all_suppliers"), *names], self)
            history_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            history_completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self.history_supplier_combo.setCompleter(history_completer)
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
        """Open the Add Supplier dialog and persist the new supplier on accept."""
        dialog = SupplierDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                SupplierService.create_supplier(**data)
            except ValueError as e:
                QMessageBox.warning(self, _t("common.validation_error"), str(e))
                return
            self.refresh_suppliers()

    def _selected_supplier(self):
        """Return the Supplier for the currently selected supplier_table row, or None."""
        row = self.supplier_table.currentIndex().row()
        if row < 0 or row >= len(self.suppliers):
            return None
        return self.suppliers[row]

    def edit_supplier(self):
        """Open the Edit Supplier dialog for the selected row and persist changes on accept (#523)."""
        supplier = self._selected_supplier()
        if not supplier:
            return

        dialog = SupplierDialog(self, supplier=supplier)
        if dialog.exec():
            data = dialog.get_data()
            try:
                SupplierService.update_supplier(supplier.id, **data)
            except ValueError as e:
                QMessageBox.warning(self, _t("common.validation_error"), str(e))
                return
            self.refresh_suppliers()

    def deactivate_supplier(self):
        """Deactivate the selected supplier after confirmation (#523).

        A soft delete via the same is_active flag Product/Customer/User
        already use -- SupplierService.update_supplier already supports it,
        this was purely an unwired UI gap.
        """
        supplier = self._selected_supplier()
        if not supplier:
            return

        reply = QMessageBox.question(
            self,
            _t("purchase.confirm_deactivate_title"),
            _t("purchase.confirm_deactivate_message", company=supplier.company_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            SupplierService.update_supplier(supplier.id, is_active=False)
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
        """Look up the searched product and add it as a new GRN line item."""
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

        self._add_grn_row(product, qty, cost)
        self.product_search.clear()
        self.update_total()

    def _add_grn_row(self, product, qty: Decimal, cost: Decimal) -> None:
        """Append one line item to the GRN grid and the underlying grn_items list."""
        self.grn_items.append({"product": product, "qty": qty, "cost": cost})

        row = self.grn_model.rowCount()
        self.grn_model.insertRow(row)
        self.grn_model.setItem(row, 0, QStandardItem(str(product.id)))
        self.grn_model.setItem(row, 1, QStandardItem(product.name_en))
        self.grn_model.setItem(row, 2, QStandardItem(str(qty)))
        self.grn_model.setItem(row, 3, QStandardItem(str(cost)))
        self.grn_model.setItem(row, 4, QStandardItem(str(qty * cost)))

    def prefill_grn_items(self, items: list[dict], purchase_order_id: int | None = None) -> None:
        """Switch to the New GRN tab and pre-fill it from Reorder's selected items.

        Each item is {product_id, product_name, barcode, current_stock,
        order_qty} (see ReorderView.create_purchase_order). Looks products
        up by barcode -- the same lookup used for manual product search --
        and skips any that no longer resolve (e.g. deactivated since the
        reorder list was built) rather than failing the whole batch.

        Args:
            purchase_order_id: the Purchase Order these items were ordered
                against, if any (#486) -- tracked so commit_grn() can flag
                received-vs-ordered discrepancies.
        """
        self.tabs.setCurrentWidget(self.grn_tab)
        self.grn_items = []
        self.grn_model.setRowCount(0)
        self.current_purchase_order_id = purchase_order_id

        for item in items:
            product = ProductService.get_by_barcode(item["barcode"])
            if not product:
                continue
            qty = item["order_qty"] if item["order_qty"] > 0 else Decimal("1.000")
            self._add_grn_row(product, qty, product.cost)

        self.update_total()

    def refresh_open_orders(self) -> None:
        """Repopulate the Open Purchase Orders combo (#486)."""
        self.open_po_combo.clear()
        self.open_po_combo.addItem(_t("purchase.select_open_order"), None)
        for order in PurchaseOrderService.get_open_orders():
            supplier_name = order.supplier.company_name if order.supplier else ""
            self.open_po_combo.addItem(f"{order.document_number} — {supplier_name}", order.id)

    def load_selected_purchase_order(self) -> None:
        """Load the Open Purchase Orders combo's current selection into the GRN grid,
        pre-filling each line with its outstanding (not yet received) quantity (#486)."""
        order_id = self.open_po_combo.currentData()
        if not order_id:
            return

        order = PurchaseOrderService.get_order(order_id)
        if not order:
            return

        self.tabs.setCurrentWidget(self.grn_tab)
        self.grn_items = []
        self.grn_model.setRowCount(0)
        self.current_purchase_order_id = order.id

        supplier_index = self.supplier_combo.findData(order.supplier_id)
        if supplier_index >= 0:
            self.supplier_combo.setCurrentIndex(supplier_index)

        for item in order.items:
            outstanding = item.qty_ordered - item.qty_received
            if outstanding <= 0:
                continue
            self._add_grn_row(item.product, outstanding, item.product.cost)

        self.update_total()

    def update_total(self):
        """Recalculate and display the running total cost of the GRN line items."""
        total = sum(item["qty"] * item["cost"] for item in self.grn_items)
        total_str = format(total, ".2f")
        self.total_label.setText(f"{_t('purchase.total_cost_label')}: {total_str}")

    def set_user(self, user):
        """Store the logged-in user for use when committing a GRN."""
        self.user = user

    def commit_grn(self):
        """Validate the GRN form, create the purchase, commit received stock, and reset the form on success."""
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
            # 1. Prepare Items
            items_data = []
            for i in range(self.grn_model.rowCount()):
                # Read from table in case user edited
                prod_id = int(self.grn_model.item(i, 0).text())
                qty = Decimal(self.grn_model.item(i, 2).text())
                cost = Decimal(self.grn_model.item(i, 3).text())

                items_data.append({"product_id": prod_id, "qty": qty, "cost": cost})

            # 2. Flag PO-vs-received discrepancies before committing anything (#486, #719)
            if self.current_purchase_order_id:
                discrepancies = PurchaseOrderService.check_receipt_discrepancies(
                    self.current_purchase_order_id, items_data
                )
                if discrepancies:
                    details = "\n".join(format_discrepancy_line(d) for d in discrepancies)
                    reply = QMessageBox.question(
                        self,
                        _t("purchase.discrepancy_title"),
                        _t("purchase.discrepancy_confirm", details=details),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return

            # 3. Create Draft
            purchase = PurchaseService.create_purchase(
                supplier_id=supplier_id,
                reference_external=ref_no,
                user_id=self.user.id,
                purchase_order_id=self.current_purchase_order_id,
            )

            # 4. Commit
            vat_text = self.input_vat_field.text().strip()
            try:
                input_vat = Decimal(vat_text) if vat_text else Decimal("0.00")
            except InvalidOperation:
                QMessageBox.warning(self, _t("common.error"), _t("purchase.error_invalid_vat"))
                return
            PurchaseService.commit_purchase(purchase.id, items_data, input_vat=input_vat)

            QMessageBox.information(
                self,
                _t("common.success"),
                _t("purchase.grn_committed_msg", doc_number=purchase.document_number),
            )

            # Reset
            self.grn_model.removeRows(0, self.grn_model.rowCount())
            self.grn_items = []
            self.invoice_input.clear()
            self.input_vat_field.clear()
            self.current_purchase_order_id = None
            self.update_total()
            self.refresh_open_orders()

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
        filter_layout.setContentsMargins(0, BAR_MARGIN_V, 0, BAR_MARGIN_V)
        filter_layout.setSpacing(BAR_ITEM_SPACING)

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

        if not suppliers:
            self.payable_supplier_table.insertRow(0)
            empty_item = QTableWidgetItem(_t("purchase.payables_empty_state"))
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(QColor("gray"))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.payable_supplier_table.setItem(0, 0, empty_item)
            self.payable_supplier_table.setSpan(0, 0, 1, self.payable_supplier_table.columnCount())
            return

        for supplier in suppliers:
            row = self.payable_supplier_table.rowCount()
            self.payable_supplier_table.insertRow(row)

            self.payable_supplier_table.setItem(row, 0, QTableWidgetItem(str(supplier.id)))
            self.payable_supplier_table.setItem(row, 1, QTableWidgetItem(supplier.company_name))
            self.payable_supplier_table.setItem(row, 2, QTableWidgetItem(supplier.phone or ""))

            payable = getattr(supplier, "current_payable", Decimal("0.00"))
            payable_item = QTableWidgetItem(f"{payable:.2f}")
            payable_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            terms = getattr(supplier, "payment_terms", 0) or 0
            if payable == 0:
                payable_item.setForeground(status_color(SUCCESS))
            elif terms > 0:
                payable_item.setForeground(status_color(WARNING))
            else:
                payable_item.setForeground(status_color(DANGER))

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
                debit_item = QTableWidgetItem(f"{entry.amount:.2f}")
                debit_item.setForeground(status_color(DANGER))
                debit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.payable_ledger_table.setItem(row, 3, debit_item)
                self.payable_ledger_table.setItem(row, 4, QTableWidgetItem(""))
                total_debit += entry.amount
            else:
                # Credit (payment reduces payable)
                self.payable_ledger_table.setItem(row, 3, QTableWidgetItem(""))
                credit_item = QTableWidgetItem(f"{abs(entry.amount):.2f}")
                credit_item.setForeground(status_color(SUCCESS))
                credit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.payable_ledger_table.setItem(row, 4, credit_item)
                total_credit += abs(entry.amount)

            balance_item = QTableWidgetItem(f"{entry.balance_after:.2f}")
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
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

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
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

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
