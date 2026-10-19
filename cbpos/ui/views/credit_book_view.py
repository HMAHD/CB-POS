import logging
from datetime import datetime
from decimal import Decimal

from PyQt6.QtCore import QDate, QSize, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.utils.formatters import format_currency, format_date, format_datetime, format_number, money_header
from cbpos.i18n import _t, register_language_callback, t_or
from cbpos.ui.constants import BAR_MARGIN_H, BAR_MARGIN_V
from cbpos.ui.dialogs.customer_editor import CustomerEditor
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, INFO, NEUTRAL, SUCCESS, WARNING, status_color
from cbpos.ui.utils.style_helpers import refresh_style
from cbpos.ui.widgets.status_pill_delegate import StatusPillDelegate, set_status_pill
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    configure_table_columns,
)

logger = logging.getLogger(__name__)


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


class CreditBookView(QWidget):
    """
    Drill-down Credit Book view.
    Page 0: Full-width customer list with search and debt indicators.
    Page 1: Selected customer's header, actions, ledger, and summary.
    """

    def __init__(self) -> None:
        """Build the two-page stack and load the customer list."""
        super().__init__()
        self.setObjectName("CreditBookView")
        self.customer_service = CustomerService()
        self.selected_customer = None
        self._showing_all_dates: bool = False
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)
        self.load_customers()

    def init_ui(self) -> None:
        """Build the customer list page and the customer detail/ledger page."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("CreditBookStack")
        layout.addWidget(self.stack)

        # ===== PAGE 0: Customer List =====
        self._build_customer_list_page()

        # ===== PAGE 1: Customer Detail / Ledger =====
        self._build_customer_detail_page()

    # ------------------------------------------------------------------
    # Page 0: Customer List
    # ------------------------------------------------------------------

    def _build_customer_list_page(self) -> None:
        page = QWidget()
        page.setObjectName("CreditListPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 16, 16, 16)
        page_layout.setSpacing(12)

        # Search & Action toolbar
        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("CreditSearchInput")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.filter_customers)
        toolbar_row.addWidget(self.search_input, 1)

        self.btn_add_customer = QPushButton()
        self.btn_add_customer.setObjectName("CreditAddBtn")
        self.btn_add_customer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_customer.clicked.connect(self.open_add_customer)
        toolbar_row.addWidget(self.btn_add_customer)

        page_layout.addLayout(toolbar_row)

        # Customer table (full width)
        self.customer_table = QTableWidget()
        self.customer_table.setObjectName("CreditCustomerTable")
        self.customer_table.setColumnCount(6)
        configure_table_columns(
            self.customer_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # ID (hidden)
                1: QHeaderView.ResizeMode.Stretch,  # Name - needs the room
                2: QHeaderView.ResizeMode.ResizeToContents,  # Phone
                3: QHeaderView.ResizeMode.ResizeToContents,  # Outstanding Debt
                4: QHeaderView.ResizeMode.ResizeToContents,  # Credit Limit
                5: QHeaderView.ResizeMode.ResizeToContents,  # Loyalty Points
            },
        )
        self.customer_table.setColumnHidden(0, True)
        self.customer_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.customer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.customer_table.setAlternatingRowColors(True)
        self.customer_table.verticalHeader().setVisible(False)
        self.customer_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.customer_table.doubleClicked.connect(self._on_customer_double_click)
        self.empty_customer_state = attach_table_empty_state(self.customer_table, Icons.CUSTOMERS, "common.no_items")
        # Rows open on double-click / Enter / right-click (#593): say so with the cursor.
        self.customer_table.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.customer_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customer_table.customContextMenuRequested.connect(self._show_customer_context_menu)
        page_layout.addWidget(self.customer_table, 1)

        open_row = QHBoxLayout()
        self.lbl_open_hint = QLabel()
        self.lbl_open_hint.setObjectName("CreditOpenHint")
        self.lbl_open_hint.setWordWrap(True)
        open_row.addWidget(self.lbl_open_hint, 1)
        self.btn_open_customer_ledger = QPushButton()
        self.btn_open_customer_ledger.setObjectName("BtnOpenCustomerLedger")
        self.btn_open_customer_ledger.clicked.connect(self._open_selected_customer)
        open_row.addWidget(self.btn_open_customer_ledger)
        page_layout.addLayout(open_row)

        # Enter opens the row only while the table has focus: Enter in the
        # search box must not open whichever row happens to be current. A
        # scan's Enter still goes to the scanner first (#548).
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self.customer_table)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._open_selected_customer)

        # Summary footer
        footer = QFrame()
        footer.setObjectName("CreditListFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(BAR_MARGIN_H, BAR_MARGIN_V, BAR_MARGIN_H, BAR_MARGIN_V)
        self.lbl_total_customers = QLabel()
        self.lbl_total_customers.setObjectName("CreditFooterLabel")
        self.lbl_total_outstanding = QLabel()
        self.lbl_total_outstanding.setObjectName("CreditFooterDebt")
        footer_layout.addWidget(self.lbl_total_customers)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_total_outstanding)
        page_layout.addWidget(footer)

        self.stack.addWidget(page)

    # ------------------------------------------------------------------
    # Page 1: Customer Detail / Ledger
    # ------------------------------------------------------------------

    def _build_customer_detail_page(self) -> None:
        page = QWidget()
        page.setObjectName("CreditDetailPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 14, 16, 14)
        page_layout.setSpacing(12)

        # 1. Navigation strip (Back button + View badge)
        nav_row = QHBoxLayout()
        self.btn_back = QPushButton()
        self.btn_back.setObjectName("CreditBackBtn")
        _set_button_icon(self.btn_back, "fa5s.arrow-left", "#00BCEB", pad_right=8, size=12)
        self.btn_back.clicked.connect(self._go_back)
        nav_row.addWidget(self.btn_back)

        nav_row.addStretch()
        self.lbl_view_badge = QLabel()
        self.lbl_view_badge.setObjectName("CreditViewBadge")
        nav_row.addWidget(self.lbl_view_badge)
        page_layout.addLayout(nav_row)

        # 2. Customer Header / Hero Card
        self.header_card = QFrame()
        self.header_card.setObjectName("CreditHeaderCard")
        header_layout = QVBoxLayout(self.header_card)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(12)

        # Top identity row: Avatar + Name/ID + Meta items
        id_row = QHBoxLayout()
        id_row.setSpacing(12)

        self.lbl_avatar = QLabel()
        self.lbl_avatar.setObjectName("CreditAvatarIcon")
        self.lbl_avatar.setFixedSize(40, 40)
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_avatar.setPixmap(Icons.get(Icons.CUSTOMER, "#00BCEB").pixmap(24, 24))
        id_row.addWidget(self.lbl_avatar)

        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_top = QHBoxLayout()
        name_top.setSpacing(8)
        self.lbl_cust_name = QLabel()
        self.lbl_cust_name.setObjectName("CreditCustName")
        name_top.addWidget(self.lbl_cust_name)
        self.lbl_cust_id = QLabel()
        self.lbl_cust_id.setObjectName("CreditCustId")
        name_top.addWidget(self.lbl_cust_id)
        name_top.addStretch()
        name_col.addLayout(name_top)

        meta_sub = QHBoxLayout()
        meta_sub.setSpacing(16)

        # Phone
        self.item_phone = QWidget()
        self.item_phone.setObjectName("MetaContainer")
        phone_layout = QHBoxLayout(self.item_phone)
        phone_layout.setContentsMargins(0, 0, 0, 0)
        phone_layout.setSpacing(6)
        self.lbl_phone_icon = QLabel()
        self.lbl_phone_icon.setPixmap(Icons.get("fa5s.phone-alt", "#94A3B8").pixmap(12, 12))
        self.lbl_cust_phone = QLabel("")
        self.lbl_cust_phone.setObjectName("CreditCustPhone")
        phone_layout.addWidget(self.lbl_phone_icon)
        phone_layout.addWidget(self.lbl_cust_phone)
        meta_sub.addWidget(self.item_phone)

        # Address
        self.item_address = QWidget()
        self.item_address.setObjectName("MetaContainer")
        addr_layout = QHBoxLayout(self.item_address)
        addr_layout.setContentsMargins(0, 0, 0, 0)
        addr_layout.setSpacing(6)
        self.lbl_address_icon = QLabel()
        self.lbl_address_icon.setPixmap(Icons.get("fa5s.map-marker-alt", "#94A3B8").pixmap(12, 12))
        self.lbl_cust_address = QLabel("")
        self.lbl_cust_address.setObjectName("CreditCustAddress")
        addr_layout.addWidget(self.lbl_address_icon)
        addr_layout.addWidget(self.lbl_cust_address)
        meta_sub.addWidget(self.item_address)

        # Company / Tier
        self.item_company = QWidget()
        self.item_company.setObjectName("MetaContainer")
        comp_layout = QHBoxLayout(self.item_company)
        comp_layout.setContentsMargins(0, 0, 0, 0)
        comp_layout.setSpacing(6)
        self.lbl_company_icon = QLabel()
        self.lbl_company_icon.setPixmap(Icons.get("fa5s.building", "#94A3B8").pixmap(12, 12))
        self.lbl_cust_tier = QLabel("")
        self.lbl_cust_tier.setObjectName("CreditCustTier")
        comp_layout.addWidget(self.lbl_company_icon)
        comp_layout.addWidget(self.lbl_cust_tier)
        meta_sub.addWidget(self.item_company)

        meta_sub.addStretch()
        name_col.addLayout(meta_sub)
        id_row.addLayout(name_col, 1)

        header_layout.addLayout(id_row)

        # Bottom row: 5 KPI stat chips
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        # Chip 1: Outstanding Debt
        self.chip_debt = QFrame()
        self.chip_debt.setObjectName("CreditKpiDebt")
        chip_debt_layout = QVBoxLayout(self.chip_debt)
        chip_debt_layout.setContentsMargins(10, 8, 10, 8)
        chip_debt_layout.setSpacing(2)
        self.lbl_kpi_debt_title = QLabel()
        self.lbl_kpi_debt_title.setObjectName("CreditKpiTitle")
        self.lbl_debt = QLabel()
        self.lbl_debt.setObjectName("CreditMetricDebt")
        chip_debt_layout.addWidget(self.lbl_kpi_debt_title)
        chip_debt_layout.addWidget(self.lbl_debt)
        kpi_row.addWidget(self.chip_debt, 1)

        # Chip 2: Available Credit
        self.chip_avail = QFrame()
        self.chip_avail.setObjectName("CreditKpiAvail")
        chip_avail_layout = QVBoxLayout(self.chip_avail)
        chip_avail_layout.setContentsMargins(10, 8, 10, 8)
        chip_avail_layout.setSpacing(2)
        self.lbl_kpi_avail_title = QLabel()
        self.lbl_kpi_avail_title.setObjectName("CreditKpiTitle")
        self.lbl_available = QLabel()
        self.lbl_available.setObjectName("CreditMetricAvail")
        chip_avail_layout.addWidget(self.lbl_kpi_avail_title)
        chip_avail_layout.addWidget(self.lbl_available)
        kpi_row.addWidget(self.chip_avail, 1)

        # Chip 3: Credit Limit
        self.chip_limit = QFrame()
        self.chip_limit.setObjectName("CreditKpiLimit")
        chip_limit_layout = QVBoxLayout(self.chip_limit)
        chip_limit_layout.setContentsMargins(10, 8, 10, 8)
        chip_limit_layout.setSpacing(2)
        self.lbl_kpi_limit_title = QLabel()
        self.lbl_kpi_limit_title.setObjectName("CreditKpiTitle")
        self.lbl_limit = QLabel()
        self.lbl_limit.setObjectName("CreditMetricLimit")
        chip_limit_layout.addWidget(self.lbl_kpi_limit_title)
        chip_limit_layout.addWidget(self.lbl_limit)
        kpi_row.addWidget(self.chip_limit, 1)

        # Chip 4: Loyalty Points
        self.chip_points = QFrame()
        self.chip_points.setObjectName("CreditKpiPoints")
        chip_points_layout = QVBoxLayout(self.chip_points)
        chip_points_layout.setContentsMargins(10, 8, 10, 8)
        chip_points_layout.setSpacing(2)
        self.lbl_kpi_points_title = QLabel()
        self.lbl_kpi_points_title.setObjectName("CreditKpiTitle")
        self.lbl_points = QLabel()
        self.lbl_points.setObjectName("CreditMetricPoints")
        chip_points_layout.addWidget(self.lbl_kpi_points_title)
        chip_points_layout.addWidget(self.lbl_points)
        kpi_row.addWidget(self.chip_points, 1)

        # Chip 5: Last Payment
        self.chip_last = QFrame()
        self.chip_last.setObjectName("CreditKpiLast")
        chip_last_layout = QVBoxLayout(self.chip_last)
        chip_last_layout.setContentsMargins(10, 8, 10, 8)
        chip_last_layout.setSpacing(2)
        self.lbl_kpi_last_title = QLabel()
        self.lbl_kpi_last_title.setObjectName("CreditKpiTitle")
        self.lbl_last_payment = QLabel()
        self.lbl_last_payment.setObjectName("CreditMetricLast")
        chip_last_layout.addWidget(self.lbl_kpi_last_title)
        chip_last_layout.addWidget(self.lbl_last_payment)
        kpi_row.addWidget(self.chip_last, 1)

        header_layout.addLayout(kpi_row)
        page_layout.addWidget(self.header_card)

        # 3. Action Buttons Bar
        action_bar = QFrame()
        action_bar.setObjectName("CreditActionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(10)

        self.btn_receive_payment = QPushButton()
        self.btn_receive_payment.setObjectName("CreditPayBtn")
        _set_button_icon(self.btn_receive_payment, Icons.PAY, "#FFFFFF", pad_right=8, size=14)
        self.btn_receive_payment.clicked.connect(self.receive_payment)
        action_layout.addWidget(self.btn_receive_payment)

        self.btn_print_statement = QPushButton()
        self.btn_print_statement.setObjectName("CreditPrintBtn")
        _set_button_icon(self.btn_print_statement, Icons.PRINT, "#00BCEB", pad_right=8, size=14)
        self.btn_print_statement.clicked.connect(self.print_statement)
        action_layout.addWidget(self.btn_print_statement)

        self.btn_adjust = QPushButton()
        self.btn_adjust.setObjectName("CreditAdjustBtn")
        _set_button_icon(self.btn_adjust, Icons.SETTINGS, "#00BCEB", pad_right=8, size=14)
        self.btn_adjust.clicked.connect(self.adjust_balance)
        action_layout.addWidget(self.btn_adjust)

        self.btn_adjust_points = QPushButton()
        self.btn_adjust_points.setObjectName("CreditAdjustPointsBtn")
        _set_button_icon(self.btn_adjust_points, Icons.POINTS, "#F59E0B", pad_right=8, size=14)
        self.btn_adjust_points.clicked.connect(self.adjust_loyalty_points)
        action_layout.addWidget(self.btn_adjust_points)

        self.btn_edit_customer = QPushButton()
        self.btn_edit_customer.setObjectName("CreditEditBtn")
        _set_button_icon(self.btn_edit_customer, Icons.EDIT, "#00BCEB", pad_right=8, size=14)
        self.btn_edit_customer.clicked.connect(self.edit_customer)
        action_layout.addWidget(self.btn_edit_customer)

        action_layout.addStretch()
        page_layout.addWidget(action_bar)

        # F1 Shortcut for Receive Payment
        self.f1_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F1), self)
        self.f1_shortcut.activated.connect(self._on_f1_shortcut)

        # 4. Date Filters & Presets Bar
        filter_bar = QFrame()
        filter_bar.setObjectName("CreditFilterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(12, 6, 12, 6)
        filter_layout.setSpacing(10)

        self.lbl_from = QLabel()
        self.lbl_from.setObjectName("CreditFilterLabel")
        filter_layout.addWidget(self.lbl_from)

        self.date_from = QDateEdit()
        self.date_from.setObjectName("CreditDateEdit")
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_from.dateChanged.connect(self._on_date_picker_changed)
        filter_layout.addWidget(self.date_from)

        self.lbl_to = QLabel()
        self.lbl_to.setObjectName("CreditFilterLabel")
        filter_layout.addWidget(self.lbl_to)

        self.date_to = QDateEdit()
        self.date_to.setObjectName("CreditDateEdit")
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self._on_date_picker_changed)
        filter_layout.addWidget(self.date_to)

        filter_layout.addSpacing(10)

        # Presets
        self.btn_preset_30d = QPushButton()
        self.btn_preset_30d.setObjectName("CreditPresetBtn30d")
        self.btn_preset_30d.setProperty("presetActive", True)
        self.btn_preset_30d.clicked.connect(lambda: self.set_date_preset("30d"))
        filter_layout.addWidget(self.btn_preset_30d)

        self.btn_preset_month = QPushButton()
        self.btn_preset_month.setObjectName("CreditPresetBtnMonth")
        self.btn_preset_month.setProperty("presetActive", False)
        self.btn_preset_month.clicked.connect(lambda: self.set_date_preset("month"))
        filter_layout.addWidget(self.btn_preset_month)

        self.btn_all_dates = QPushButton()
        self.btn_all_dates.setObjectName("CreditAllDatesBtn")
        self.btn_all_dates.setProperty("presetActive", False)
        self.btn_all_dates.clicked.connect(self.show_all_dates)
        filter_layout.addWidget(self.btn_all_dates)

        filter_layout.addStretch()
        page_layout.addWidget(filter_bar)

        # 5. Range-mismatch hint (#284)
        self.credit_range_hint = QFrame()
        self.credit_range_hint.setObjectName("CreditRangeHint")
        hint_layout = QHBoxLayout(self.credit_range_hint)
        hint_layout.setContentsMargins(12, 8, 12, 8)
        hint_layout.setSpacing(10)

        self.lbl_hint_icon = QLabel()
        self.lbl_hint_icon.setObjectName("CreditRangeHintIcon")
        self.lbl_hint_icon.setPixmap(Icons.get(Icons.WARNING, "#F59E0B").pixmap(16, 16))
        hint_layout.addWidget(self.lbl_hint_icon)

        self.lbl_credit_range_hint = QLabel()
        self.lbl_credit_range_hint.setObjectName("CreditRangeHintLabel")
        self.lbl_credit_range_hint.setWordWrap(True)
        hint_layout.addWidget(self.lbl_credit_range_hint, 1)

        self.btn_credit_range_hint_show_all = QPushButton()
        self.btn_credit_range_hint_show_all.setObjectName("CreditRangeHintBtn")
        self.btn_credit_range_hint_show_all.clicked.connect(self.show_all_dates)
        hint_layout.addWidget(self.btn_credit_range_hint_show_all)

        self.credit_range_hint.setVisible(False)
        page_layout.addWidget(self.credit_range_hint)

        # 6. Ledger Table (full width)
        self.ledger_table = QTableWidget()
        self.ledger_table.setObjectName("CreditLedgerTable")
        self.ledger_table.setColumnCount(6)
        configure_table_columns(
            self.ledger_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.Stretch,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
                5: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        self.ledger_table.setItemDelegateForColumn(1, StatusPillDelegate(self.ledger_table))
        self.empty_ledger_state = attach_table_empty_state(self.ledger_table, Icons.CREDIT_BOOK, "common.no_items")
        self.ledger_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ledger_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ledger_table.setAlternatingRowColors(True)
        self.ledger_table.verticalHeader().setVisible(False)
        self.ledger_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page_layout.addWidget(self.ledger_table, 1)

        # 7. Footer Summary
        footer = QFrame()
        footer.setObjectName("CreditLedgerFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(16)
        self.lbl_total_sales = QLabel()
        self.lbl_total_sales.setObjectName("CreditLedgerDebit")
        self.lbl_total_payments = QLabel()
        self.lbl_total_payments.setObjectName("CreditLedgerCredit")
        self.lbl_closing = QLabel()
        self.lbl_closing.setObjectName("CreditLedgerClosing")
        footer_layout.addWidget(self.lbl_total_sales)
        footer_layout.addWidget(self.lbl_total_payments)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_closing)
        page_layout.addWidget(footer)

        self.stack.addWidget(page)

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.btn_add_customer.setText(_t("credit_book.btn_add_customer"))
        self.btn_open_customer_ledger.setText(_t("credit_book.btn_open_customer_ledger"))
        self.lbl_open_hint.setText(_t("credit_book.row_open_hint"))
        self.btn_open_customer_ledger.setToolTip(_t("credit_book.row_open_hint"))
        self.search_input.setPlaceholderText(_t("credit_book.search_placeholder"))
        self.customer_table.setHorizontalHeaderLabels(
            [
                _t("credit_book.customer_header_id"),
                _t("credit_book.customer_header_name"),
                _t("credit_book.customer_header_phone"),
                money_header(_t("credit_book.customer_header_debt")),
                money_header(_t("credit_book.customer_header_limit")),
                _t("credit_book.customer_header_points"),
            ]
        )
        align_numeric_headers(self.customer_table, (3, 4, 5))  # Debt, Limit, Points

        self.btn_back.setText(_t("credit_book.btn_back").replace("<", "").strip())
        self.lbl_view_badge.setText(t_or("credit_book.view_badge", "CUSTOMER CREDIT LEDGER"))
        self.btn_receive_payment.setText(_t("credit_book.btn_receive_payment") + " (F1)")
        self.btn_print_statement.setText(_t("credit_book.btn_print_statement"))
        self.btn_adjust.setText(_t("credit_book.btn_adjust_balance"))
        self.btn_adjust_points.setText(_t("credit_book.btn_adjust_points"))
        self.btn_edit_customer.setText(_t("credit_book.btn_edit_customer"))
        self.lbl_from.setText(_t("credit_book.from"))
        self.lbl_to.setText(_t("credit_book.to"))
        self.btn_preset_30d.setText(t_or("credit_book.preset_30d", "Last 30 Days"))
        self.btn_preset_month.setText(t_or("credit_book.preset_month", "This Month"))
        self.btn_all_dates.setText(_t("credit_book.all"))
        self.btn_credit_range_hint_show_all.setText(_t("credit_book.all"))

        self.lbl_kpi_debt_title.setText(t_or("credit_book.kpi_debt", "OUTSTANDING DEBT"))
        self.lbl_kpi_avail_title.setText(t_or("credit_book.kpi_available", "AVAILABLE CREDIT"))
        self.lbl_kpi_limit_title.setText(t_or("credit_book.kpi_limit", "CREDIT LIMIT"))
        self.lbl_kpi_points_title.setText(t_or("credit_book.kpi_points", "LOYALTY POINTS"))
        self.lbl_kpi_last_title.setText(t_or("credit_book.kpi_last_payment", "LAST PAYMENT"))

        self.ledger_table.setHorizontalHeaderLabels(
            [
                _t("credit_book.ledger_header_date"),
                _t("credit_book.ledger_header_type"),
                _t("credit_book.ledger_header_doc"),
                money_header(_t("credit_book.ledger_header_debit")),
                money_header(_t("credit_book.ledger_header_credit")),
                money_header(_t("credit_book.ledger_header_balance")),
            ]
        )
        align_numeric_headers(self.ledger_table, (3, 4, 5))  # Debit, Credit, Balance

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_customer_double_click(self, index) -> None:
        """Drill into the selected customer's ledger."""
        self._open_customer_row(index.row())

    def _open_selected_customer(self) -> None:
        """Drill into the currently selected customer's ledger (button/Enter key)."""
        self._open_customer_row(self.customer_table.currentRow())

    def _open_customer_row(self, row: int) -> None:
        """Drill into the ledger for the given table row."""
        customer = self._load_customer_row(row)
        if customer:
            self.update_header(customer)
            self.set_date_preset("30d")
            self.stack.setCurrentIndex(1)

    def _on_f1_shortcut(self) -> None:
        """Handle F1 key shortcut to receive payment on detail page."""
        if self.stack.currentIndex() == 1 and self.btn_receive_payment.isEnabled():
            self.receive_payment()

    def _load_customer_row(self, row: int):
        """Make the customer on ``row`` the selected customer and return it (None for no/empty row)."""
        if row < 0:
            return None
        customer_id_item = self.customer_table.item(row, 0)
        if not customer_id_item or not customer_id_item.text().isdigit():
            return None
        customer = self.customer_service.get_customer(int(customer_id_item.text()))
        if customer:
            self.selected_customer = customer
        return customer

    def _show_customer_context_menu(self, pos) -> None:
        """Right-click menu for the customer under the cursor (#593).

        The row under the cursor is selected and loaded *before* any action
        runs, so Receive Payment / Edit act on the customer that was clicked,
        never on one opened earlier.
        """
        index = self.customer_table.indexAt(pos)
        if not index.isValid():
            return
        self.customer_table.setCurrentCell(index.row(), 1)
        customer = self._load_customer_row(index.row())
        if not customer:
            return

        menu = QMenu(self)
        open_action = QAction(_t("credit_book.btn_open_customer_ledger"), menu)
        open_action.triggered.connect(self._open_selected_customer)
        menu.addAction(open_action)

        pay_action = QAction(_t("credit_book.btn_receive_payment"), menu)
        pay_action.setEnabled((customer.current_debt or 0) > 0)
        pay_action.triggered.connect(self.receive_payment)
        menu.addAction(pay_action)

        edit_action = QAction(_t("credit_book.btn_edit_customer"), menu)
        edit_action.triggered.connect(self.edit_customer)
        menu.addAction(edit_action)

        if ConfigService.get("enable_loyalty"):
            points_action = QAction(_t("credit_book.btn_adjust_points"), menu)
            points_action.triggered.connect(lambda: self.adjust_loyalty_points(customer))
            menu.addAction(points_action)

        menu.exec(self.customer_table.viewport().mapToGlobal(pos))

    def _go_back(self) -> None:
        """Return to the customer list and forget the opened customer (#593)."""
        self.selected_customer = None
        self.stack.setCurrentIndex(0)
        self._refresh_customer_list()

    def _refresh_customer_list(self) -> None:
        """Reload the list, keeping the search filter and the current row's customer selected."""
        current = self.customer_table.item(self.customer_table.currentRow(), 0)
        current_id = current.text() if current else None
        self.filter_customers(self.search_input.text())
        if current_id is None:
            return
        for row in range(self.customer_table.rowCount()):
            item = self.customer_table.item(row, 0)
            if item and item.text() == current_id:
                self.customer_table.setCurrentCell(row, 1)
                break

    # ========== Customer List Methods ==========

    def load_customers(self) -> None:
        """Load all active customers into the table."""
        customers = self.customer_service.get_all_customers()
        self.populate_customer_table(customers)

    def filter_customers(self, text: str) -> None:
        """Filter customers by search text."""
        if not text:
            self.load_customers()
            return
        customers = self.customer_service.search_customers(text)
        self.populate_customer_table(customers)

    def populate_customer_table(self, customers: list) -> None:
        """Populate the customer table with color-coded debt status."""
        self.customer_table.setRowCount(0)

        if not customers:
            self.customer_table.insertRow(0)
            empty_item = QTableWidgetItem(_t("credit_book.no_customers_found"))
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(status_color(NEUTRAL))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.customer_table.setItem(0, 0, empty_item)
            self.customer_table.setSpan(0, 0, 1, self.customer_table.columnCount())
            self.lbl_total_customers.setText(_t("credit_book.customer_count", count=0))
            self.lbl_total_outstanding.setText(
                _t("credit_book.total_outstanding", amount=format_currency(Decimal("0.00")))
            )
            return

        total_outstanding = Decimal("0.00")

        for customer in customers:
            row = self.customer_table.rowCount()
            self.customer_table.insertRow(row)

            self.customer_table.setItem(row, 0, QTableWidgetItem(str(customer.id)))
            name_item = QTableWidgetItem(customer.name)
            name_item.setToolTip(_t("credit_book.row_open_hint"))
            self.customer_table.setItem(row, 1, name_item)
            self.customer_table.setItem(row, 2, QTableWidgetItem(customer.phone or ""))

            # Debt with color coding
            debt_item = QTableWidgetItem(format_number(customer.current_debt, 2))
            debt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            limit_item = QTableWidgetItem(format_number(customer.credit_limit, 2))
            limit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            if customer.credit_limit > 0:
                ratio = customer.current_debt / customer.credit_limit
                if ratio >= Decimal("0.9"):
                    debt_item.setForeground(status_color(DANGER))
                elif ratio >= Decimal("0.5"):
                    debt_item.setForeground(status_color(WARNING))
                elif customer.current_debt == 0:
                    debt_item.setForeground(status_color(SUCCESS))
            elif customer.current_debt > 0:
                debt_item.setForeground(status_color(DANGER))

            points_item = QTableWidgetItem(format_number(customer.loyalty_points or 0, 0))
            points_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.customer_table.setItem(row, 3, debt_item)
            self.customer_table.setItem(row, 4, limit_item)
            self.customer_table.setItem(row, 5, points_item)

            total_outstanding += customer.current_debt

        # Update footer
        count = len(customers)
        self.lbl_total_customers.setText(_t("credit_book.customer_count", count=count))
        self.lbl_total_outstanding.setText(
            _t("credit_book.total_outstanding", amount=format_currency(total_outstanding))
        )

    def update_header(self, customer) -> None:
        """Update the header card with customer details."""
        self.lbl_cust_name.setText(customer.name)
        cid = getattr(customer, "id", None)
        self.lbl_cust_id.setText(f"#CUST-{cid:04d}" if isinstance(cid, int) else f"#{cid or ''}")

        phone = getattr(customer, "phone", None)
        if phone:
            self.lbl_cust_phone.setText(str(phone))
            self.lbl_phone_icon.setVisible(True)
            self.item_phone.setVisible(True)
        else:
            self.lbl_cust_phone.setText(_t("credit_book.no_phone"))
            self.lbl_phone_icon.setVisible(False)
            self.item_phone.setVisible(True)

        address = getattr(customer, "address", None)
        if address:
            self.lbl_cust_address.setText(str(address))
            self.item_address.setVisible(True)
        else:
            self.lbl_cust_address.setText("")
            self.item_address.setVisible(False)

        company = getattr(customer, "company_name", None)
        if company:
            self.lbl_cust_tier.setText(str(company))
            self.item_company.setVisible(True)
        else:
            self.lbl_cust_tier.setText("")
            self.item_company.setVisible(False)

        summary = CustomerCreditService.get_customer_summary(customer.id) if cid else None
        if summary:
            self.lbl_debt.setText(format_currency(summary["current_debt"]))
            self.lbl_available.setText(format_currency(summary["available"]))
            self.lbl_limit.setText(format_currency(summary["credit_limit"]))
            if summary.get("last_payment_date"):
                self.lbl_last_payment.setText(format_date(summary["last_payment_date"]))
            else:
                self.lbl_last_payment.setText(_t("credit_book.none"))
        else:
            debt = getattr(customer, "current_debt", Decimal("0.00")) or Decimal("0.00")
            limit = getattr(customer, "credit_limit", Decimal("0.00")) or Decimal("0.00")
            self.lbl_debt.setText(format_currency(debt))
            self.lbl_limit.setText(format_currency(limit))
            self.lbl_available.setText(format_currency(max(Decimal("0.00"), limit - debt)))
            self.lbl_last_payment.setText(_t("credit_book.none"))

        if ConfigService.get("enable_loyalty"):
            self.chip_points.setVisible(True)
            self.lbl_points.setText(str(getattr(customer, "loyalty_points", 0) or 0))
            self.btn_adjust_points.setVisible(True)
        else:
            self.chip_points.setVisible(False)
            self.btn_adjust_points.setVisible(False)

    # ========== Ledger Methods ==========

    def set_date_preset(self, preset: str) -> None:
        """Set date filter preset ('30d', 'month', or 'all')."""
        if not self.selected_customer:
            return

        if preset == "all":
            self.show_all_dates()
            return

        self._showing_all_dates = False
        self._update_preset_buttons(preset)

        today = QDate.currentDate()
        self.date_from.blockSignals(True)
        self.date_to.blockSignals(True)
        if preset == "30d":
            self.date_from.setDate(today.addDays(-30))
            self.date_to.setDate(today)
        elif preset == "month":
            self.date_from.setDate(QDate(today.year(), today.month(), 1))
            self.date_to.setDate(today)
        self.date_from.blockSignals(False)
        self.date_to.blockSignals(False)

        self.reload_ledger()

    def _on_date_picker_changed(self) -> None:
        """Called when user manually edits either date picker."""
        self._showing_all_dates = False
        self._update_preset_buttons(None)
        self.reload_ledger()

    def _update_preset_buttons(self, active_preset: str | None) -> None:
        """Update visual active state on preset buttons."""
        buttons = [
            ("30d", self.btn_preset_30d),
            ("month", self.btn_preset_month),
            ("all", self.btn_all_dates),
        ]
        for name, btn in buttons:
            is_active = name == active_preset
            btn.setProperty("presetActive", is_active)
            refresh_style(btn)

    def reload_ledger(self) -> None:
        """Reload ledger entries based on selected customer and date filters."""
        if not self.selected_customer:
            return

        self._showing_all_dates = False
        date_from = datetime(
            self.date_from.date().year(),
            self.date_from.date().month(),
            self.date_from.date().day(),
        )
        date_to = datetime(
            self.date_to.date().year(),
            self.date_to.date().month(),
            self.date_to.date().day(),
            23,
            59,
            59,
        )

        entries = CustomerCreditService.get_ledger(
            self.selected_customer.id,
            date_from=date_from,
            date_to=date_to,
        )
        self.populate_ledger(entries)

    def show_all_dates(self) -> None:
        """Show all ledger entries (no date filter)."""
        if not self.selected_customer:
            return

        self._showing_all_dates = True
        self._update_preset_buttons("all")

        entries = CustomerCreditService.get_ledger(self.selected_customer.id)

        # If entries exist, sync the date pickers without re-triggering reload
        if entries:
            timestamps = [e.timestamp for e in entries if e.timestamp]
            if timestamps:
                earliest = min(timestamps)
                latest = max(timestamps)
                self.date_from.blockSignals(True)
                self.date_to.blockSignals(True)
                self.date_from.setDate(QDate(earliest.year, earliest.month, earliest.day))
                self.date_to.setDate(QDate(latest.year, latest.month, latest.day))
                self.date_from.blockSignals(False)
                self.date_to.blockSignals(False)

        self.populate_ledger(entries)

    def populate_ledger(self, entries: list) -> None:
        """Populate the ledger table with entries."""
        self.ledger_table.setRowCount(0)

        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        closing_balance = Decimal("0.00")

        if not entries:
            self.ledger_table.setRowCount(1)
            has_any = (
                not self._showing_all_dates
                and bool(self.selected_customer)
                and len(CustomerCreditService.get_ledger(self.selected_customer.id)) > 0
            )
            msg = _t("credit_book.ledger_empty_range") if has_any else _t("credit_book.ledger_no_history")
            empty_item = QTableWidgetItem(msg)
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(status_color(NEUTRAL))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.ledger_table.setItem(0, 0, empty_item)
            self.ledger_table.setSpan(0, 0, 1, self.ledger_table.columnCount())
            self.ledger_table.setRowHeight(0, 60)

            # Update footer
            self.lbl_total_sales.setText(_t("credit_book.sales_label") + " " + format_currency(total_debit))
            self.lbl_total_payments.setText(_t("credit_book.payments_label") + " " + format_currency(total_credit))
            self.lbl_closing.setText(_t("credit_book.closing_label") + " " + format_currency(closing_balance))
            self._update_credit_range_hint(closing_balance)
            return

        for entry in entries:
            row = self.ledger_table.rowCount()
            self.ledger_table.insertRow(row)

            # Date
            date_str = format_datetime(entry.timestamp) if entry.timestamp else ""
            self.ledger_table.setItem(row, 0, QTableWidgetItem(date_str))

            # Type
            type_item = QTableWidgetItem(entry.entry_type)
            type_upper = (entry.entry_type or "").upper()
            if type_upper == "PAYMENT":
                meaning = SUCCESS
            elif type_upper == "SALE":
                meaning = WARNING
            elif type_upper == "ADJUSTMENT":
                meaning = INFO
            elif type_upper == "OPENING":
                meaning = NEUTRAL
            else:
                meaning = NEUTRAL
            set_status_pill(type_item, entry.entry_type, meaning)
            self.ledger_table.setItem(row, 1, type_item)

            # Doc #
            self.ledger_table.setItem(row, 2, QTableWidgetItem(entry.reference_doc or entry.note or ""))

            # Debit / Credit
            if entry.amount > 0:
                debit_item = QTableWidgetItem(format_number(entry.amount, 2))
                debit_item.setForeground(status_color(DANGER))
                debit_item.setTextAlignment(NUMERIC_ALIGNMENT)
                self.ledger_table.setItem(row, 3, debit_item)
                self.ledger_table.setItem(row, 4, QTableWidgetItem(""))
                total_debit += entry.amount
            else:
                self.ledger_table.setItem(row, 3, QTableWidgetItem(""))
                credit_item = QTableWidgetItem(format_number(abs(entry.amount), 2))
                credit_item.setForeground(status_color(SUCCESS))
                credit_item.setTextAlignment(NUMERIC_ALIGNMENT)
                self.ledger_table.setItem(row, 4, credit_item)
                total_credit += abs(entry.amount)

            # Balance
            balance_item = QTableWidgetItem(format_number(entry.balance_after, 2))
            balance_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.ledger_table.setItem(row, 5, balance_item)

            closing_balance = entry.balance_after

        # Update footer
        self.lbl_total_sales.setText(_t("credit_book.sales_label") + " " + format_currency(total_debit))
        self.lbl_total_payments.setText(_t("credit_book.payments_label") + " " + format_currency(total_credit))
        self.lbl_closing.setText(_t("credit_book.closing_label") + " " + format_currency(closing_balance))

        self._update_credit_range_hint(closing_balance)

    def _update_credit_range_hint(self, visible_closing_balance: Decimal) -> None:
        """Warn when the filtered ledger doesn't account for the customer's
        full outstanding debt (#284)."""
        if not self.selected_customer:
            self.credit_range_hint.setVisible(False)
            return

        # When viewing all dates, date-range mismatch hint is not applicable
        if self._showing_all_dates:
            self.credit_range_hint.setVisible(False)
            return

        summary = CustomerCreditService.get_customer_summary(self.selected_customer.id)
        actual_balance = summary["current_debt"] if summary else Decimal("0.00")

        if actual_balance != visible_closing_balance:
            self.lbl_credit_range_hint.setText(
                _t("credit_book.credit_range_hint", balance=format_currency(actual_balance))
            )
            self.credit_range_hint.setVisible(True)
        else:
            self.credit_range_hint.setVisible(False)

    # ========== Action Methods ==========

    def receive_payment(self) -> None:
        """Open the Receive Payment dialog for the selected customer."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.CREDIT_RECEIVE_PAYMENT, self):
            return

        if not self.selected_customer:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        if self.selected_customer.current_debt <= 0:
            QMessageBox.information(
                self,
                _t("credit_book.no_debt_title"),
                _t("credit_book.no_debt_msg"),
            )
            return

        from cbpos.ui.dialogs.receive_payment_dialog import ReceivePaymentDialog

        dialog = ReceivePaymentDialog(self.selected_customer.id, self)
        if dialog.exec():
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)
            self.reload_ledger()
            if self.stack.currentIndex() == 0:
                self._refresh_customer_list()

    def print_statement(self) -> None:
        """Open customer statement dialog for viewing and printing."""
        if not self.selected_customer:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        from cbpos.ui.dialogs.customer_statement_dialog import (
            CustomerStatementDialog,
        )

        dialog = CustomerStatementDialog(self.selected_customer, self)
        dialog.exec()

    def adjust_balance(self) -> None:
        """Adjust the customer's balance (correction)."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.ui.dialogs.adjust_balance_dialog import AdjustBalanceDialog

        if not check_permission_with_override(Permissions.CREDIT_ADJUST_BALANCE, self):
            return

        if not self.selected_customer:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        dlg = AdjustBalanceDialog(self.selected_customer, self)
        if dlg.exec():
            QMessageBox.information(
                self,
                _t("credit_book.done_title"),
                _t("credit_book.balance_adjusted_msg"),
            )
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)
            self.reload_ledger()

    def adjust_loyalty_points(self, customer=None) -> None:
        """Adjust the customer's loyalty points with permission check and required reason."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.ui.dialogs.adjust_points_dialog import AdjustPointsDialog

        if not check_permission_with_override(Permissions.LOYALTY_ADJUST_POINTS, self):
            return

        target = customer or self.selected_customer
        if not target:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        dlg = AdjustPointsDialog(target, self)
        if dlg.exec():
            if self.selected_customer and self.selected_customer.id == target.id:
                self.selected_customer = self.customer_service.get_customer(target.id)
                self.update_header(self.selected_customer)
            self._refresh_customer_list()

    def edit_customer(self) -> None:
        """Open the customer editor for the selected customer."""
        if not self.selected_customer:
            QMessageBox.warning(
                self,
                _t("credit_book.no_customer_title"),
                _t("credit_book.no_customer_msg"),
            )
            return

        dialog = CustomerEditor(self.selected_customer, parent=self)
        if dialog.exec():
            self.selected_customer = self.customer_service.get_customer(self.selected_customer.id)
            self.update_header(self.selected_customer)
            if self.stack.currentIndex() == 0:
                self._refresh_customer_list()

    def open_add_customer(self) -> None:
        """Open dialog to add a new customer."""
        dialog = CustomerEditor(parent=self)
        if dialog.exec():
            self.load_customers()
