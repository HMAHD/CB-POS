import contextlib
import logging
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.refund_service import RefundService
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency, format_datetime, format_relative_time
from cbpos.i18n import _t
from cbpos.ui.refund_messages import refund_confirm_text, refund_done_text
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, INFO, NEUTRAL, SUCCESS, WARNING, status_color, status_hex
from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    RelativeTimeTableWidgetItem,
    StatusPillDelegate,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
    set_status_pill,
)

logger = logging.getLogger(__name__)


class SaleHistoryDialog(QDialog):
    """Dialog to browse recent sales and inspect authentic system receipts."""

    def __init__(self, parent=None):
        """Build the dialog defaulting to today's sales."""
        super().__init__(parent)
        self.setObjectName("SaleHistoryDialog")
        self.setWindowTitle(_t("sale_history.title"))
        self.setMinimumSize(1000, 650)
        self.resize(1050, 700)

        self._sales: list = []
        self._selected_sale = None
        self._active_filter = "today"

        # Debounce timer for search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._load_sales)

        self._init_ui()
        self.retranslate_ui()
        self._load_sales()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # --- Quick filter & search bar ---
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)

        self._filter_buttons: dict[str, QPushButton] = {}
        for key in ("today", "yesterday", "this_week", "this_month"):
            btn = QPushButton()
            btn.setObjectName("QuickFilterBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda checked, k=key: self._on_filter_clicked(k))
            filter_bar.addWidget(btn)
            self._filter_buttons[key] = btn

        filter_bar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setObjectName("SaleHistorySearch")
        self.search_input.setMinimumWidth(260)
        self.search_input.setMaximumWidth(340)
        self.search_input.textChanged.connect(self._on_search_changed)
        filter_bar.addWidget(self.search_input)

        layout.addLayout(filter_bar)

        # --- Horizontal Splitter: Master sales table (left) + Receipt inspector (right) ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("SaleHistorySplitter")

        # Left: sales table
        self.sales_table = QTableWidget()
        self.sales_table.setObjectName("SaleHistoryTable")
        self.sales_table.setColumnCount(5)
        self.sales_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sales_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sales_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sales_table.setAlternatingRowColors(True)
        self.sales_table.verticalHeader().setVisible(False)
        self.sales_table.horizontalHeader().setStretchLastSection(False)
        configure_table_columns(
            self.sales_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Interactive,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.Stretch,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        self.sales_table.setColumnWidth(0, 140)
        align_numeric_headers(self.sales_table.horizontalHeader(), (3,))
        self.sales_table.setItemDelegateForColumn(4, StatusPillDelegate(self.sales_table))
        attach_table_empty_state(self.sales_table, Icons.SALES, "sale_history.no_sales_found")
        self.sales_table.currentItemChanged.connect(self._on_sale_selected)
        self.sales_table.cellClicked.connect(self._on_table_cell_clicked)
        self.splitter.addWidget(self.sales_table)

        # Right: details panel (Digital Inspector - Variant A)
        self.details_widget = QFrame()
        self.details_widget.setObjectName("SaleHistoryDetails")
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(12, 12, 12, 12)
        details_layout.setSpacing(8)

        self.lbl_details_title = QLabel()
        self.lbl_details_title.setProperty("class", "bold")
        details_layout.addWidget(self.lbl_details_title)

        # Prompt label (shown when no sale selected)
        self.lbl_select_prompt = QLabel()
        self.lbl_select_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_select_prompt.setProperty("class", "transparent")
        details_layout.addWidget(self.lbl_select_prompt, 1)

        # Inspector Content Container (shown when a sale is selected)
        self.inspector_content = QWidget()
        insp_layout = QVBoxLayout(self.inspector_content)
        insp_layout.setContentsMargins(0, 0, 0, 0)
        insp_layout.setSpacing(8)

        # Header Row: Clickable Invoice Badge (Copy to clipboard) + Status Pill
        header_row = QHBoxLayout()
        self.btn_copy_invoice = QPushButton()
        self.btn_copy_invoice.setObjectName("InvoiceBadge")
        self.btn_copy_invoice.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_invoice.clicked.connect(self._on_copy_invoice_clicked)
        header_row.addWidget(self.btn_copy_invoice)

        header_row.addStretch()

        self.lbl_info_status = QLabel()
        self.lbl_info_status.setProperty("class", "bold")
        header_row.addWidget(self.lbl_info_status)
        insp_layout.addLayout(header_row)

        # Sub-header: Date & Time
        self.lbl_info_date = QLabel()
        self.lbl_info_date.setProperty("class", "transparent")
        insp_layout.addWidget(self.lbl_info_date)

        # Metadata Card (3-column grid)
        self.meta_card = QFrame()
        self.meta_card.setObjectName("SaleMetadataCard")
        meta_layout = QGridLayout(self.meta_card)
        meta_layout.setContentsMargins(8, 6, 8, 6)
        meta_layout.setHorizontalSpacing(16)
        meta_layout.setVerticalSpacing(4)

        self.lbl_hdr_cashier = QLabel()
        self.lbl_hdr_cashier.setProperty("class", "transparent")
        self.lbl_info_cashier = QLabel()
        self.lbl_info_cashier.setProperty("class", "bold")

        self.lbl_hdr_customer = QLabel()
        self.lbl_hdr_customer.setProperty("class", "transparent")
        self.lbl_info_customer = QLabel()
        self.lbl_info_customer.setProperty("class", "bold")

        self.lbl_hdr_payment = QLabel()
        self.lbl_hdr_payment.setProperty("class", "transparent")
        self.lbl_info_payment = QLabel()
        self.lbl_info_payment.setProperty("class", "bold")

        meta_layout.addWidget(self.lbl_hdr_cashier, 0, 0)
        meta_layout.addWidget(self.lbl_info_cashier, 1, 0)
        meta_layout.addWidget(self.lbl_hdr_customer, 0, 1)
        meta_layout.addWidget(self.lbl_info_customer, 1, 1)
        meta_layout.addWidget(self.lbl_hdr_payment, 0, 2)
        meta_layout.addWidget(self.lbl_info_payment, 1, 2)

        insp_layout.addWidget(self.meta_card)

        # Line Items Table
        self.items_table = QTableWidget()
        self.items_table.setObjectName("SaleHistoryItems")
        self.items_table.setColumnCount(4)
        configure_table_columns(
            self.items_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        align_numeric_headers(self.items_table.horizontalHeader(), (1, 2, 3))
        attach_table_empty_state(self.items_table, Icons.SALES, "common.no_items")
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.setAlternatingRowColors(True)
        insp_layout.addWidget(self.items_table, 1)

        # Financial Summary Card
        self.summary_card = QFrame()
        self.summary_card.setObjectName("SaleSummaryCard")
        sum_layout = QGridLayout(self.summary_card)
        sum_layout.setContentsMargins(8, 6, 8, 6)
        sum_layout.setHorizontalSpacing(16)
        sum_layout.setVerticalSpacing(4)

        self.lbl_sum_subtotal_hdr = QLabel()
        self.lbl_sum_subtotal_hdr.setProperty("class", "transparent")
        self.lbl_sum_subtotal_val = QLabel()
        self.lbl_sum_subtotal_val.setProperty("class", "transparent")
        self.lbl_sum_subtotal_val.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_sum_discount_hdr = QLabel()
        self.lbl_sum_discount_hdr.setProperty("class", "transparent")
        self.lbl_sum_discount_val = QLabel()
        self.lbl_sum_discount_val.setProperty("class", "transparent")
        self.lbl_sum_discount_val.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_sum_tax_hdr = QLabel()
        self.lbl_sum_tax_hdr.setProperty("class", "transparent")
        self.lbl_sum_tax_val = QLabel()
        self.lbl_sum_tax_val.setProperty("class", "transparent")
        self.lbl_sum_tax_val.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_sum_total_hdr = QLabel()
        self.lbl_sum_total_hdr.setProperty("class", "bold")
        self.lbl_sum_total_val = QLabel()
        self.lbl_sum_total_val.setProperty("class", "bold")
        self.lbl_sum_total_val.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_sum_tendered_val = QLabel()
        self.lbl_sum_tendered_val.setProperty("class", "transparent")
        self.lbl_sum_change_val = QLabel()
        self.lbl_sum_change_val.setProperty("class", "transparent")
        self.lbl_sum_change_val.setAlignment(Qt.AlignmentFlag.AlignRight)

        sum_layout.addWidget(self.lbl_sum_subtotal_hdr, 0, 0)
        sum_layout.addWidget(self.lbl_sum_subtotal_val, 0, 1)
        sum_layout.addWidget(self.lbl_sum_discount_hdr, 1, 0)
        sum_layout.addWidget(self.lbl_sum_discount_val, 1, 1)
        sum_layout.addWidget(self.lbl_sum_tax_hdr, 2, 0)
        sum_layout.addWidget(self.lbl_sum_tax_val, 2, 1)
        sum_layout.addWidget(self.lbl_sum_total_hdr, 3, 0)
        sum_layout.addWidget(self.lbl_sum_total_val, 3, 1)
        sum_layout.addWidget(self.lbl_sum_tendered_val, 4, 0)
        sum_layout.addWidget(self.lbl_sum_change_val, 4, 1)

        insp_layout.addWidget(self.summary_card)

        # Action Buttons inside Inspector
        insp_btn_layout = QHBoxLayout()
        insp_btn_layout.addStretch()

        self.btn_refund = QPushButton()
        self.btn_refund.setObjectName("SaleHistoryRefund")
        self.btn_refund.setProperty("class", "danger")
        self.btn_refund.clicked.connect(self._start_refund)
        insp_btn_layout.addWidget(self.btn_refund)

        insp_layout.addLayout(insp_btn_layout)
        details_layout.addWidget(self.inspector_content, 1)

        self.splitter.addWidget(self.details_widget)
        self.splitter.setSizes([620, 420])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        layout.addWidget(self.splitter, 1)

        # --- Action bar ---
        self.action_bar = QWidget()
        action_layout = QHBoxLayout(self.action_bar)
        action_layout.setContentsMargins(0, 4, 0, 0)

        self.lbl_record_count = QLabel()
        self.lbl_record_count.setProperty("class", "transparent")
        action_layout.addWidget(self.lbl_record_count)

        action_layout.addStretch()

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("BtnCancel")
        self.btn_close.setProperty("class", "secondary")
        self.btn_close.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_close)

        layout.addWidget(self.action_bar)

        # Retained compatibility widgets for test and API safety
        self._init_retained_compat_widgets()

        # Set default filter
        self._filter_buttons["today"].setChecked(True)

        # Initial state: hide detail info, show prompt
        self._show_detail_state(False)

    def _init_retained_compat_widgets(self) -> None:
        """Keep widgets referenced by tests initialized but hidden from visible UI."""
        self.info_frame = QFrame()
        self.info_frame.setVisible(False)
        self.lbl_info_receipt = QLabel(self.info_frame)

        self.btn_reprint = QPushButton()
        self.btn_reprint.setVisible(False)
        self.btn_reprint.clicked.connect(self._reprint_receipt)

        self.refund_panel = QFrame()
        self.refund_panel.setVisible(False)
        self.lbl_refund_header = QLabel(self.refund_panel)
        self.lbl_refund_reason = QLabel(self.refund_panel)
        self.txt_refund_reason = QTextEdit(self.refund_panel)
        self.btn_confirm_refund = QPushButton(self.refund_panel)
        self.btn_confirm_refund.clicked.connect(self._confirm_refund)
        self.btn_cancel_refund = QPushButton(self.refund_panel)
        self.btn_cancel_refund.clicked.connect(self._cancel_refund)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setVisible(False)
        self.receipt_preview = ReceiptPreviewWidget(self.preview_scroll)

    def retranslate_ui(self) -> None:
        """Apply all translatable text."""
        self.setWindowTitle(_t("sale_history.title"))

        filter_keys = {
            "today": "sale_history.filter_today",
            "yesterday": "sale_history.filter_yesterday",
            "this_week": "sale_history.filter_this_week",
            "this_month": "sale_history.filter_this_month",
        }
        for key, i18n_key in filter_keys.items():
            self._filter_buttons[key].setText(_t(i18n_key))

        self.search_input.setPlaceholderText(_t("sale_history.search_placeholder"))

        self.sales_table.setHorizontalHeaderLabels(
            [
                _t("sale_history.col_receipt"),
                _t("sale_history.col_datetime"),
                _t("sale_history.col_customer"),
                _t("sale_history.col_total"),
                _t("sale_history.col_status"),
            ]
        )
        align_numeric_headers(self.sales_table.horizontalHeader(), (3,))

        self.lbl_details_title.setText(_t("sale_history.sale_details"))
        self.lbl_select_prompt.setText(_t("sale_history.select_sale_prompt"))
        self.btn_close.setText(_t("sale_history.btn_close"))
        self.btn_refund.setText(_t("sale_history.btn_refund"))

        self.lbl_hdr_cashier.setText(_t("sale_history.detail_cashier"))
        self.lbl_hdr_customer.setText(_t("sale_history.detail_customer"))
        self.lbl_hdr_payment.setText(_t("sale_history.detail_payment"))

        self.lbl_sum_subtotal_hdr.setText(_t("sale_history.subtotal"))
        self.lbl_sum_discount_hdr.setText(_t("sale_history.discount"))
        self.lbl_sum_tax_hdr.setText(_t("sale_history.tax"))
        self.lbl_sum_total_hdr.setText(_t("sale_history.grand_total"))

        self.items_table.setHorizontalHeaderLabels(
            [
                _t("sale_history.col_product"),
                _t("sale_history.col_qty"),
                _t("sale_history.col_unit_price"),
                _t("sale_history.col_subtotal"),
            ]
        )
        align_numeric_headers(self.items_table.horizontalHeader(), (1, 2, 3))

        # Retained widget labels for tests
        self.btn_reprint.setText(_t("sale_history.btn_reprint"))
        self.lbl_refund_reason.setText(_t("sale_history.refund_reason_label"))
        self.txt_refund_reason.setPlaceholderText(_t("sale_history.refund_reason_placeholder"))
        self.btn_cancel_refund.setText(_t("sale_history.btn_cancel_refund"))
        self.btn_confirm_refund.setText(_t("sale_history.btn_confirm_refund"))

    # ── Filter logic ──────────────────────────────────────────────

    def _on_filter_clicked(self, key: str) -> None:
        """Handle quick filter button click."""
        self._active_filter = key
        for k, btn in self._filter_buttons.items():
            btn.setChecked(k == key)
        self._load_sales()

    def _on_search_changed(self, text: str) -> None:
        """Restart debounce timer on search text change."""
        self._search_timer.start()

    def _get_date_range(self) -> tuple[datetime, datetime]:
        """Return (from_date, to_date) based on active filter."""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if self._active_filter == "today":
            return today_start, now
        elif self._active_filter == "yesterday":
            yesterday = today_start - timedelta(days=1)
            return yesterday, today_start - timedelta(seconds=1)
        elif self._active_filter == "this_week":
            week_start = today_start - timedelta(days=today_start.weekday())
            return week_start, now
        elif self._active_filter == "this_month":
            month_start = today_start.replace(day=1)
            return month_start, now
        return today_start, now

    # ── Data loading ──────────────────────────────────────────────

    def _load_sales(self) -> None:
        """Fetch sales from service and populate the table."""
        from_date, to_date = self._get_date_range()
        search_term = self.search_input.text().strip() or None

        query_from = None if search_term else from_date
        query_to = None if search_term else to_date

        try:
            self._sales = SaleQueryService.get_sales_history(
                from_date=query_from,
                to_date=query_to,
                search_term=search_term,
                limit=500,
            )
        except Exception as e:
            logger.error("Failed to load sales history: %s", e)
            self._sales = []

        self._populate_sales_table()
        self._selected_sale = None
        self._show_detail_state(False)
        self.btn_reprint.setEnabled(False)
        self.btn_refund.setEnabled(False)

    def _populate_sales_table(self) -> None:
        """Fill the sales table with loaded data."""
        with batch_table_update(self.sales_table):
            self.sales_table.setRowCount(0)

            if not self._sales:
                # Show empty state
                self.sales_table.setRowCount(1)
                item = QTableWidgetItem(_t("sale_history.no_sales_found"))
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.sales_table.setItem(0, 0, item)
                self.sales_table.setSpan(0, 0, 1, 5)
                self.lbl_record_count.setText(_t("sale_history.no_sales_found"))
                return

            self.lbl_record_count.setText(_t("sale_history.sales_found", count=len(self._sales)))

            sale_ids = [sale.id for sale in self._sales if getattr(sale, "id", None)]
            self._refund_states = RefundService.refund_states(sale_ids) if sale_ids else {}

            TableItem = QTableWidgetItem
            RelTimeItem = RelativeTimeTableWidgetItem
            fmt_curr = format_currency
            num_align = NUMERIC_ALIGNMENT
            user_role = Qt.ItemDataRole.UserRole
            align_center = Qt.AlignmentFlag.AlignCenter
            set_pill = set_status_pill
            succ_color = status_color(SUCCESS)
            dang_color = status_color(DANGER)
            warn_color = status_color(WARNING)
            info_color = status_color(INFO)
            walk_in_text = _t("sale_history.walk_in")
            set_item = self.sales_table.setItem
            insert_row = self.sales_table.insertRow

            for idx, sale in enumerate(self._sales):
                row = self.sales_table.rowCount()
                insert_row(row)

                # Receipt #
                receipt_item = TableItem(sale.document_number or f"#{sale.id}")
                receipt_item.setData(user_role, idx)
                set_item(row, 0, receipt_item)

                # Date/Time
                set_item(row, 1, RelTimeItem(sale.date))

                # Customer
                customer_name = sale.customer.name if sale.customer else walk_in_text
                set_item(row, 2, TableItem(customer_name))

                # Total (right-aligned)
                total_item = TableItem(fmt_curr(sale.total_amount))
                total_item.setTextAlignment(num_align)
                set_item(row, 3, total_item)

                # Status (colored & derived refund state #915)
                status = sale.status or "COMPLETED"
                rstate = self._refund_states.get(sale.id, "NONE")
                is_refund_doc = sale.payment_method == "REFUND" or bool(getattr(sale, "refund_of_sale_id", None))

                status_item = TableItem()
                if status == "VOID":
                    status_text = self._get_status_display(status)
                    status_item.setForeground(dang_color)
                    set_pill(status_item, status_text, "danger")
                elif is_refund_doc:
                    status_text = (
                        _t("sale_history.status_refunded")
                        if _t("sale_history.status_refunded") != "sale_history.status_refunded"
                        else "REFUND"
                    )
                    status_item.setForeground(warn_color)
                    set_pill(status_item, status_text, "warning")
                elif rstate == "FULL":
                    status_text = _t("history.pill_refunded")
                    status_item.setForeground(info_color)
                    set_pill(status_item, status_text, "info")
                elif rstate == "PARTIAL":
                    status_text = _t("history.pill_part_refunded")
                    status_item.setForeground(info_color)
                    set_pill(status_item, status_text, "info")
                elif status == "COMPLETED":
                    status_text = self._get_status_display(status)
                    status_item.setForeground(succ_color)
                    set_pill(status_item, status_text, "success")
                else:
                    status_text = self._get_status_display(status)
                    set_pill(status_item, status_text, "neutral")

                status_item.setTextAlignment(align_center)
                set_item(row, 4, status_item)

    def _get_status_display(self, status: str) -> str:
        """Return translated status text."""
        status_map = {
            "COMPLETED": _t("sale_history.status_completed"),
            "VOID": _t("sale_history.status_void"),
        }
        return status_map.get(status, status)

    # ── Sale selection ────────────────────────────────────────────

    def _on_sale_selected(
        self,
        current: QTableWidgetItem | None = None,
        previous: QTableWidgetItem | None = None,
    ) -> None:
        """Populate details panel when a sale row is selected."""
        if not current:
            self._selected_sale = None
            self._show_detail_state(False)
            self.btn_reprint.setEnabled(False)
            self.btn_refund.setEnabled(False)
            return

        row = current.row()
        first_cell = self.sales_table.item(row, 0)
        if not first_cell:
            return

        idx = first_cell.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._sales):
            return

        sale = self._sales[idx]
        self._selected_sale = sale
        self._show_detail_state(True)

        doc_num = str(getattr(sale, "document_number", None) or sale.id)
        status = sale.status or "COMPLETED"

        # Update invoice badge button
        self.btn_copy_invoice.setText(f"📋 {doc_num}")
        self.btn_copy_invoice.setToolTip(_t("sale_history.copy_invoice_tooltip"))
        self.lbl_info_receipt.setText(f"{_t('sale_history.detail_receipt')} {doc_num}")

        # Status indicator
        rstate = getattr(self, "_refund_states", {}).get(sale.id, "NONE")
        is_refund_doc = sale.payment_method == "REFUND" or bool(getattr(sale, "refund_of_sale_id", None))

        if status == "VOID":
            status_text = self._get_status_display(status)
            meaning = DANGER
        elif is_refund_doc:
            status_text = "REFUND"
            meaning = WARNING
        elif rstate == "FULL":
            status_text = _t("history.pill_refunded")
            meaning = INFO
        elif rstate == "PARTIAL":
            status_text = _t("history.pill_part_refunded")
            meaning = INFO
        elif status == "COMPLETED":
            status_text = self._get_status_display(status)
            meaning = SUCCESS
        else:
            status_text = self._get_status_display(status)
            meaning = NEUTRAL

        self.lbl_info_status.setText(status_text)
        self.lbl_info_status.setStyleSheet(f"color: {status_hex(meaning)}; font-weight: bold;")

        # Date & relative time
        if getattr(sale, "date", None):
            date_str = format_datetime(sale.date)
            rel_date = format_relative_time(sale.date)
            date_display = f"{rel_date} • {date_str}"
            self.lbl_info_date.setToolTip(date_str)
        else:
            date_display = "N/A"
            self.lbl_info_date.setToolTip("")
        self.lbl_info_date.setText(date_display)

        # Metadata grid
        customer_name = sale.customer.name if getattr(sale, "customer", None) else _t("sale_history.walk_in")
        cashier_name = sale.user.username if getattr(sale, "user", None) else "N/A"
        payment_method = sale.payment_method or "N/A"

        self.lbl_info_cashier.setText(cashier_name)
        self.lbl_info_customer.setText(customer_name)
        self.lbl_info_payment.setText(payment_method)

        # Populate line items
        with batch_table_update(self.items_table):
            self.items_table.setRowCount(0)
            TableItem = QTableWidgetItem
            fmt_curr = format_currency
            num_align = NUMERIC_ALIGNMENT
            set_item = self.items_table.setItem
            insert_row = self.items_table.insertRow
            unknown_prod = (
                _t("common.unknown_product")
                if _t("common.unknown_product") != "common.unknown_product"
                else "Unknown Item"
            )

            for item in sale.items or []:
                r = self.items_table.rowCount()
                insert_row(r)

                product_name = item.product.name_en if getattr(item, "product", None) else unknown_prod
                set_item(r, 0, TableItem(product_name))

                qty_item = TableItem(str(item.qty))
                qty_item.setTextAlignment(num_align)
                set_item(r, 1, qty_item)

                price_item = TableItem(fmt_curr(item.unit_price))
                price_item.setTextAlignment(num_align)
                set_item(r, 2, price_item)

                sub_item = TableItem(fmt_curr(item.subtotal))
                sub_item.setTextAlignment(num_align)
                set_item(r, 3, sub_item)

        # Summary values
        net_rev = getattr(sale, "net_revenue", None)
        subtotal_val = net_rev if net_rev is not None else sale.total_amount
        disc_val = getattr(sale, "additional_discount_value", 0) or 0
        vat_val = getattr(sale, "tax_vat", 0) or 0
        sscl_val = getattr(sale, "tax_sscl", 0) or 0
        tax_total = vat_val + sscl_val

        self.lbl_sum_subtotal_val.setText(format_currency(subtotal_val))
        self.lbl_sum_discount_val.setText(format_currency(disc_val))
        self.lbl_sum_tax_val.setText(format_currency(tax_total))
        self.lbl_sum_total_val.setText(format_currency(sale.total_amount))

        tendered_val = getattr(sale, "tendered", None)
        change_val = getattr(sale, "change", None)
        if tendered_val is not None and change_val is not None:
            self.lbl_sum_tendered_val.setText(f"{_t('sale_history.tendered')}: {format_currency(tendered_val)}")
            self.lbl_sum_change_val.setText(f"{_t('sale_history.change')}: {format_currency(change_val)}")
            self.lbl_sum_tendered_val.setVisible(True)
            self.lbl_sum_change_val.setVisible(True)
        else:
            self.lbl_sum_tendered_val.setVisible(False)
            self.lbl_sum_change_val.setVisible(False)

        # Enable/disable refund button (#915)
        can_refund = status == "COMPLETED" and not is_refund_doc and rstate != "FULL"
        self.btn_refund.setEnabled(can_refund)
        if rstate == "FULL":
            self.btn_refund.setToolTip(_t("history.refund_disabled_full"))
        elif is_refund_doc:
            self.btn_refund.setToolTip(_t("history.void_disabled_is_refund"))
        else:
            self.btn_refund.setToolTip("")

        # Retained compatibility
        if status == "VOID":
            self.btn_reprint.setEnabled(False)
            self.btn_reprint.setToolTip(_t("reprint.void_blocked"))
        else:
            self.btn_reprint.setEnabled(True)
            self.btn_reprint.setToolTip("")
        try:
            commands = ReceiptBuilder.build_receipt(sale)
            self.receipt_preview.set_commands(commands)
        except Exception:
            self.receipt_preview.set_commands([])

    def _show_detail_state(self, has_selection: bool) -> None:
        """Toggle between prompt label and digital inspector content."""
        self.lbl_select_prompt.setVisible(not has_selection)
        self.inspector_content.setVisible(has_selection)
        if not has_selection:
            self.btn_refund.setEnabled(False)
            self.btn_reprint.setEnabled(False)
            self.btn_reprint.setToolTip("")
            self.receipt_preview.set_commands([])

    def _copy_invoice_to_clipboard(self, invoice_no: str) -> None:
        """Copy invoice number to system clipboard and provide instant visual feedback."""
        if not invoice_no:
            return
        QGuiApplication.clipboard().setText(invoice_no)
        QToolTip.showText(QCursor.pos(), _t("sale_history.copied_to_clipboard", invoice=invoice_no), self)

        if hasattr(self, "btn_copy_invoice") and self.btn_copy_invoice.isVisible():
            orig_text = self.btn_copy_invoice.text()
            self.btn_copy_invoice.setText(f"✓ {_t('sale_history.copied')}")
            QTimer.singleShot(
                1500,
                lambda: self.btn_copy_invoice.setText(orig_text) if self._selected_sale else None,
            )

    def _on_copy_invoice_clicked(self) -> None:
        """Handle copy button click on inspector invoice badge."""
        if self._selected_sale:
            doc_num = getattr(self._selected_sale, "document_number", None) or str(self._selected_sale.id)
            self._copy_invoice_to_clipboard(str(doc_num))

    def _on_table_cell_clicked(self, row: int, col: int) -> None:
        """Copy receipt number when column 0 is clicked."""
        if col == 0:
            item = self.sales_table.item(row, col)
            if item and item.text():
                self._copy_invoice_to_clipboard(item.text().strip())

    # ── Reprint ───────────────────────────────────────────────────

    def _reprint_receipt(self) -> None:
        """Reprint receipt for the selected sale."""
        if not self._selected_sale:
            return

        sale = self._selected_sale
        if getattr(sale, "status", "") == "VOID":
            QMessageBox.warning(self, _t("common.warning"), _t("reprint.void_blocked"))
            return

        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.receipt_reprint_service import ReceiptReprintService
        from cbpos.core.utils.permission_helper import check_permission_with_override

        authorized_user = check_permission_with_override(Permissions.SALES_REPRINT, self)
        if not authorized_user:
            return

        current_user = AuthService.get_current_user()
        if not current_user and hasattr(self, "user"):
            current_user = self.user

        def _get_id(u):
            if not u:
                return None
            try:
                val = getattr(u, "__dict__", {}).get("id")
                if val is not None:
                    return val
            except Exception:
                pass
            try:
                from sqlalchemy import inspect

                insp = inspect(u)
                if insp and insp.identity:
                    return insp.identity[0]
            except Exception:
                pass
            try:
                return u.id
            except Exception:
                return None

        curr_id = _get_id(current_user)
        auth_id = _get_id(authorized_user)
        user_id = curr_id or auth_id
        approver_id = auth_id if (auth_id and curr_id and auth_id != curr_id) else None

        try:
            job = ReceiptReprintService.reprint(
                sale.id,
                user_id=user_id,
                approver_id=approver_id,
            )
            from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

            worker = PrintWorker.instance()
            # PrintWorker.add_job() only queues the job -- the print itself
            # happens later, asynchronously, on the worker thread. Showing
            # "success" right after add_job() (the old behavior) meant the
            # user was told the reprint worked even when the printer wasn't
            # configured at all. Wait for the real outcome instead. Guard
            # against reconnecting on every call the same way
            # ReceiptOptionsDialog.print_thermal() does.
            try:
                worker.error_occurred.disconnect(self._on_reprint_error)
            except TypeError as e:
                logger.debug("Signal not connected yet: %s", e)
            with contextlib.suppress(TypeError):
                worker.job_completed.disconnect(self._on_reprint_finished)
            worker.error_occurred.connect(self._on_reprint_error)
            worker.job_completed.connect(self._on_reprint_finished)
            worker.add_job("print_receipt", job.commands)
        except ValueError as e:
            if str(e) == "reprint_void":
                QMessageBox.warning(self, _t("common.warning"), _t("reprint.void_blocked"))
            else:
                QMessageBox.critical(self, _t("common.error"), _t("sale_history.reprint_failed"))
        except Exception as e:
            logger.error("Reprint failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), _t("sale_history.reprint_failed"))

    def _on_reprint_finished(self) -> None:
        """Called once the queued print job actually completes."""
        QMessageBox.information(self, _t("sale_history.title"), _t("sale_history.reprint_success"))

    def _on_reprint_error(self, message: str) -> None:
        """Called if the queued print job actually fails (e.g. no printer configured)."""
        logger.error("Reprint failed: %s", message)
        QMessageBox.critical(self, _t("common.error"), _t("sale_history.reprint_failed"))

    # ── Refund flow ───────────────────────────────────────────────

    def _start_refund(self) -> None:
        """Open RefundDialog pre-loaded with selected sale."""
        if not self._selected_sale:
            return

        sale = self._selected_sale
        status = sale.status or "COMPLETED"
        rstate = getattr(self, "_refund_states", {}).get(sale.id, "NONE")
        is_refund_doc = sale.payment_method == "REFUND" or bool(getattr(sale, "refund_of_sale_id", None))
        if status == "VOID" or is_refund_doc or rstate == "FULL":
            msg = (
                _t("history.refund_disabled_full")
                if rstate == "FULL"
                else _t("sale_history.refund_not_eligible", status=status)
            )
            QMessageBox.warning(
                self,
                _t("common.warning"),
                msg,
            )
            return

        from cbpos.ui.dialogs.refund_dialog import RefundDialog

        dlg = RefundDialog(self)
        dlg.load_sale(sale)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_sales()

    def _cancel_refund(self) -> None:
        """Hide refund panel, restore action bar."""
        self.refund_panel.setVisible(False)
        self.action_bar.setVisible(True)

    def _confirm_refund(self) -> None:
        """Process the refund after permission check and confirmation."""
        if not self._selected_sale:
            return

        reason = self.txt_refund_reason.toPlainText().strip()
        if not reason:
            QMessageBox.warning(
                self,
                _t("common.warning"),
                _t("sale_history.refund_reason_placeholder"),
            )
            return

        # Permission check
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        authorized_user = check_permission_with_override(Permissions.SALES_REFUND, self)
        if not authorized_user:
            return

        # Confirmation -- what is handed back vs. taken off credit (#715)
        sale = self._selected_sale
        breakdown = TransactionService.refund_breakdown(sale.id)
        if breakdown is None:
            QMessageBox.critical(self, _t("common.error"), _t("common.unknown_error"))
            return
        reply = QMessageBox.question(
            self,
            _t("common.confirm"),
            refund_confirm_text(sale.document_number, breakdown, reason),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_confirm_refund.setEnabled(False)
        try:
            success = TransactionService.process_refund(
                original_sale_id=sale.id,
                refund_reason=reason,
                user_id=authorized_user.id,
            )
            if success:
                QMessageBox.information(
                    self,
                    _t("common.success"),
                    refund_done_text(sale.document_number, breakdown),
                )
                self._cancel_refund()
                self._load_sales()
            else:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("common.unknown_error"),
                )
        except ValueError as e:
            logger.warning("Refund validation failed: %s", e)
            QMessageBox.warning(self, _t("common.warning"), translate_error(str(e)))
        except Exception as e:
            logger.exception("Refund failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
        finally:
            self.btn_confirm_refund.setEnabled(True)
