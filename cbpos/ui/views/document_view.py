import contextlib
import html
import logging
from datetime import date, datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.document_browser_service import DocumentBrowserService
from cbpos.core.services.proforma_service import ProformaService
from cbpos.core.services.refund_service import RefundService
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import (
    format_currency,
    format_datetime,
    format_discount,
    format_document_status,
    format_payment_method,
    format_quantity,
    format_relative_time,
)
from cbpos.i18n import _t, register_language_callback
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.components.activation import Activatable
from cbpos.ui.dialogs.void_reason_dialog import VoidReasonDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, INFO, NEUTRAL, SUCCESS, WARNING, pill_colors
from cbpos.ui.widgets.status_pill_delegate import StatusPillDelegate, set_status_pill
from cbpos.ui.widgets.table_helpers import (
    RelativeTimeTableWidgetItem,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)

logger = logging.getLogger(__name__)


class DocumentBrowserView(QWidget, Activatable):
    """
    Unified document browser: the document list keeps the full height, and
    the selected document's details open in a panel beside it (#612), so the
    arrow keys browse the list while the details follow.
    """

    convert_to_sale_requested = pyqtSignal(dict)

    # Status -> palette meaning (theme-aware colours, #559). DRAFT and
    # SUSPENDED differ: a draft is unfinished work, a suspended sale is
    # parked and waiting to be resumed.
    STATUS_MEANINGS = {
        "COMPLETED": SUCCESS,
        "VOID": DANGER,
        "QUOTE": INFO,
        "EXPIRED": NEUTRAL,
        "CONVERTED": SUCCESS,
        "DRAFT": NEUTRAL,
        "SUSPENDED": WARNING,
    }

    # Side detail panel (#612)
    DETAIL_PANEL_MIN_WIDTH = 360
    ITEMS_MIN_HEIGHT = 120
    ITEMS_FIT_MAX_ROWS = 15
    USER_COLUMN = 6  # hidden while the panel (which shows the user) is open

    def __init__(self) -> None:
        """Build the filter bar, document table, and detail panel, then load the first page."""
        super().__init__()
        self.setObjectName("DocumentBrowserView")
        self.current_doc: dict | None = None
        self.current_page = 1
        self.total_docs = 0
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)
        try:
            self.load_documents()
        except Exception as e:
            logger.error("Failed to load documents on init: %s", e)

    def init_ui(self) -> None:
        """Build the filter bar, document table, detail panel, and pagination bar."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title row
        title_row = QHBoxLayout()
        title_row.addStretch(1)

        self.new_proforma_btn = QPushButton()
        self.new_proforma_btn.setObjectName("DocNewQuotationBtn")
        self.new_proforma_btn.clicked.connect(self.open_proforma_dialog)
        title_row.addWidget(self.new_proforma_btn)
        layout.addLayout(title_row)

        # Nothing on this screen explained what it's for -- a flat table
        # of every document type with filter controls, but no indication
        # of when a shop owner would come here (#293).
        self.lbl_subtitle = QLabel()
        self.lbl_subtitle.setWordWrap(True)
        self.lbl_subtitle.setProperty("class", "muted")
        layout.addWidget(self.lbl_subtitle)

        # Filter Bar
        filter_frame = QFrame()
        filter_frame.setObjectName("DocFilterBar")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(8)

        self.lbl_type = QLabel()
        self.lbl_type.setObjectName("DocFilterLabel")
        filter_layout.addWidget(self.lbl_type)
        self.type_combo = QComboBox()
        self.type_combo.setObjectName("DocFilterCombo")
        self.type_combo.setMinimumWidth(110)
        filter_layout.addWidget(self.type_combo)

        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("DocFilterLabel")
        filter_layout.addWidget(self.lbl_status)
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("DocFilterCombo")
        self.status_combo.setMinimumWidth(110)
        filter_layout.addWidget(self.status_combo)

        from cbpos.ui.widgets.date_range_picker import DateRangePicker

        self.lbl_from = QLabel()
        self.lbl_from.setObjectName("DocFilterLabel")
        self.lbl_to = QLabel()
        self.lbl_to.setObjectName("DocFilterLabel")

        self.date_picker = DateRangePicker(
            self,
            default_start=date.today().replace(day=1),
            default_end=date.today(),
            default_preset="this_month",
        )
        self.from_date = self.date_picker.start_date_edit
        self.from_date.setObjectName("DocDateEdit")
        self.to_date = self.date_picker.end_date_edit
        self.to_date.setObjectName("DocDateEdit")
        self.date_picker.preset_combo.setObjectName("DocFilterCombo")
        filter_layout.addWidget(self.date_picker)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("DocSearchInput")
        self.search_input.returnPressed.connect(self.apply_filter)
        filter_layout.addWidget(self.search_input, 1)

        self.filter_btn = QPushButton()
        self.filter_btn.setObjectName("DocFilterBtn")
        self.filter_btn.clicked.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_btn)

        self.clear_btn = QPushButton()
        self.clear_btn.setObjectName("DocClearBtn")
        self.clear_btn.setProperty("class", "secondary")
        self.clear_btn.clicked.connect(self.clear_filter)
        filter_layout.addWidget(self.clear_btn)

        layout.addWidget(filter_frame)

        # Document Table (full width)
        self.doc_table = QTableWidget()
        self.doc_table.setObjectName("DocTable")
        self.doc_table.setColumnCount(7)
        configure_table_columns(
            self.doc_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # Date
                1: QHeaderView.ResizeMode.ResizeToContents,  # Doc #
                2: QHeaderView.ResizeMode.ResizeToContents,  # Type
                3: QHeaderView.ResizeMode.Stretch,  # Customer/Supplier - needs the room
                4: QHeaderView.ResizeMode.ResizeToContents,  # Total
                5: QHeaderView.ResizeMode.ResizeToContents,  # Status
                6: QHeaderView.ResizeMode.ResizeToContents,  # User
            },
            minimum_section_size=80,
        )
        self.doc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.doc_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.doc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.doc_table.verticalHeader().setVisible(False)
        self.doc_table.setAlternatingRowColors(True)
        self.doc_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.doc_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.doc_table.setItemDelegateForColumn(5, StatusPillDelegate(self.doc_table))  # Status (#560)
        self.empty_doc_state = attach_table_empty_state(self.doc_table, Icons.DOCUMENTS, "common.no_items")

        # List and details side by side (#612): the list keeps every row of
        # height, the panel takes the right-hand side only while it's open.
        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setObjectName("DocBodySplitter")
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.addWidget(self.doc_table)
        self._build_detail_panel()
        self.body_splitter.addWidget(self.detail_panel)
        self.body_splitter.setStretchFactor(0, 1)
        self.body_splitter.setStretchFactor(1, 0)
        self._detail_sized = False
        layout.addWidget(self.body_splitter, 1)

        # Pagination bar
        page_bar = QFrame()
        page_bar.setObjectName("DocPaginationBar")
        page_layout = QHBoxLayout(page_bar)
        page_layout.setContentsMargins(0, 4, 0, 4)
        page_layout.addStretch()

        self.page_label = QLabel()
        self.page_label.setObjectName("DocPageLabel")
        page_layout.addWidget(self.page_label)

        self.prev_btn = QPushButton()
        self.prev_btn.setObjectName("DocPrevBtn")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        page_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton()
        self.next_btn.setObjectName("DocNextBtn")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        page_layout.addWidget(self.next_btn)

        layout.addWidget(page_bar)

    def _build_detail_panel(self) -> None:
        """Build the right-hand detail panel: header bar, scrollable summary + line items, actions."""
        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("DocDetailPanel")
        self.detail_panel.setMinimumWidth(self.DETAIL_PANEL_MIN_WIDTH)
        self.detail_panel.setVisible(False)
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 10)
        detail_layout.setSpacing(8)

        # Header bar: title + Close
        header = QFrame()
        header.setObjectName("DocDetailHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 8, 8)
        header_layout.setSpacing(8)
        self.detail_title = QLabel(header)
        self.detail_title.setObjectName("DocDetailTitle")
        self.detail_title.setWordWrap(True)
        header_layout.addWidget(self.detail_title, 1)
        self.btn_close_detail = QPushButton(header)
        self.btn_close_detail.setObjectName("DocDetailCloseBtn")
        self.btn_close_detail.setProperty("class", "secondary")
        self.btn_close_detail.clicked.connect(self._close_detail)
        header_layout.addWidget(self.btn_close_detail, 0, Qt.AlignmentFlag.AlignTop)
        detail_layout.addWidget(header)

        # Summary, payments and line items scroll together on short screens
        scroll = QScrollArea()
        scroll.setObjectName("DocDetailScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("DocDetailContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 0, 12, 0)
        content_layout.setSpacing(8)

        self.details_label = QLabel()
        self.details_label.setObjectName("DocInfoLabel")
        self.details_label.setWordWrap(True)
        self.details_label.setTextFormat(Qt.TextFormat.RichText)
        content_layout.addWidget(self.details_label)

        self.payment_label = QLabel("")
        self.payment_label.setObjectName("DocPaymentLabel")
        self.payment_label.setWordWrap(True)
        content_layout.addWidget(self.payment_label)

        self.lbl_items_title = QLabel()
        self.lbl_items_title.setObjectName("DocItemsTitle")
        content_layout.addWidget(self.lbl_items_title)

        self.items_table = QTableWidget()
        self.items_table.setObjectName("DocItemsTable")
        self.items_table.setColumnCount(5)
        configure_table_columns(
            self.items_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,  # Product
                1: QHeaderView.ResizeMode.ResizeToContents,  # Qty
                2: QHeaderView.ResizeMode.ResizeToContents,  # Unit Price
                3: QHeaderView.ResizeMode.ResizeToContents,  # Discount
                4: QHeaderView.ResizeMode.ResizeToContents,  # Total
            },
            minimum_section_size=70,
        )
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.setMinimumHeight(self.ITEMS_MIN_HEIGHT)
        self.items_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.empty_items_state = attach_table_empty_state(self.items_table, Icons.INVENTORY, "common.no_items")
        content_layout.addWidget(self.items_table, 1)
        scroll.setWidget(content)
        detail_layout.addWidget(scroll, 1)

        # Actions: only the ones that apply to this document are shown, two per row
        self.reprint_btn = QPushButton()
        self.reprint_btn.setObjectName("DocReprintBtn")
        self.reprint_btn.clicked.connect(self.reprint_document)

        self.convert_btn = QPushButton()
        self.convert_btn.setObjectName("DocConvertBtn")
        self.convert_btn.clicked.connect(self.convert_proforma)

        self.refund_btn = QPushButton()
        self.refund_btn.setObjectName("DocRefundBtn")
        self.refund_btn.clicked.connect(self.process_refund)

        self.void_btn = QPushButton()
        self.void_btn.setObjectName("DocVoidBtn")
        self.void_btn.setProperty("class", "danger")
        self.void_btn.clicked.connect(self.void_document)

        self.transfer_btn = QPushButton()
        self.transfer_btn.setObjectName("DocTransferBtn")
        self.transfer_btn.clicked.connect(self.transfer_order)

        self._action_buttons = (self.reprint_btn, self.convert_btn, self.refund_btn, self.transfer_btn, self.void_btn)
        self._action_grid = QGridLayout()
        self._action_grid.setContentsMargins(12, 0, 12, 0)
        self._action_grid.setSpacing(8)
        detail_layout.addLayout(self._action_grid)
        self.reset_action_buttons()

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.lbl_subtitle.setText(_t("document_browser.subtitle"))
        self.new_proforma_btn.setText(_t("document_browser.btn_new_proforma"))

        # Filter labels
        self.lbl_type.setText(_t("document_browser.filter_type"))
        self.lbl_status.setText(_t("document_browser.filter_status"))
        self.lbl_from.setText(_t("document_browser.filter_from"))
        self.lbl_to.setText(_t("document_browser.filter_to"))
        self.search_input.setPlaceholderText(_t("document_browser.search_placeholder"))
        self.filter_btn.setText(_t("document_browser.btn_filter"))
        self.clear_btn.setText(_t("document_browser.btn_clear"))

        # Type combo
        current_type = self.type_combo.currentIndex()
        self.type_combo.clear()
        self.type_combo.addItems(
            [
                _t("document_browser.type_all"),
                _t("document_browser.type_sales"),
                _t("document_browser.type_purchases"),
                _t("document_browser.type_proforma"),
            ]
        )
        if 0 <= current_type < self.type_combo.count():
            self.type_combo.setCurrentIndex(current_type)

        # Status combo
        current_status = self.status_combo.currentIndex()
        self.status_combo.clear()
        self.status_combo.addItems(
            [
                _t("document_browser.status_all"),
                _t("document_browser.status_completed"),
                _t("document_browser.status_void"),
                _t("document_browser.status_draft"),
                _t("document_browser.status_quote"),
                _t("document_browser.status_expired"),
                _t("document_browser.status_converted"),
            ]
        )
        if 0 <= current_status < self.status_combo.count():
            self.status_combo.setCurrentIndex(current_status)

        # Table headers
        self.doc_table.setHorizontalHeaderLabels(
            [
                _t("document_browser.header_date"),
                _t("document_browser.header_doc_number"),
                _t("document_browser.header_type"),
                _t("document_browser.header_party"),
                _t("document_browser.header_total"),
                _t("document_browser.header_status"),
                _t("document_browser.header_user"),
            ]
        )
        align_numeric_headers(self.doc_table, (4,))  # Total

        # Detail panel
        self.detail_title.setText(_t("document_browser.detail_title"))
        self.details_label.setText(_t("document_browser.detail_empty"))
        self.btn_close_detail.setText(_t("document_browser.btn_close"))
        self.lbl_items_title.setText(_t("document_browser.detail_line_items"))
        self.items_table.setHorizontalHeaderLabels(
            [
                _t("document_browser.item_header_product"),
                _t("document_browser.item_header_qty"),
                _t("document_browser.item_header_unit_price"),
                _t("document_browser.item_header_discount"),
                _t("document_browser.item_header_total"),
            ]
        )
        align_numeric_headers(self.items_table, (1, 2, 3, 4))  # Qty, Unit Price, Discount, Total

        # Action buttons
        self.reprint_btn.setText(_t("document_browser.btn_reprint"))
        self.convert_btn.setText(_t("document_browser.btn_convert_to_sale"))
        self.refund_btn.setText(_t("document_browser.btn_refund"))
        self.void_btn.setText(_t("document_browser.btn_void"))
        self.transfer_btn.setText(_t("document_browser.btn_transfer"))

        # Pagination
        self.prev_btn.setText(_t("document_browser.btn_previous"))
        self.next_btn.setText(_t("document_browser.btn_next"))

    # ------------------------------------------------------------------
    # Detail Panel
    # ------------------------------------------------------------------

    def _hide_detail_panel(self) -> None:
        """Hide the panel; the list gets its full width and the User column back."""
        self.detail_panel.setVisible(False)
        self.doc_table.setColumnHidden(self.USER_COLUMN, False)

    def _close_detail(self) -> None:
        """Hide the detail panel."""
        self._hide_detail_panel()
        self.current_doc = None
        self.reset_action_buttons()

    def _show_detail(self) -> None:
        """Show the detail panel beside the list, at about a third of the width the first time.

        The panel repeats the user, so the list hides that column and gives
        the width to the customer/supplier name.
        """
        self.doc_table.setColumnHidden(self.USER_COLUMN, True)
        self.detail_panel.setVisible(True)
        if not self._detail_sized:
            self._detail_sized = True
            total = self.body_splitter.width()
            panel = max(self.DETAIL_PANEL_MIN_WIDTH, total * 3 // 8)
            self.body_splitter.setSizes([max(0, total - panel), panel])

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def apply_filter(self) -> None:
        """Apply filters and reload documents."""
        self.current_page = 1
        self.load_documents()

    def clear_filter(self) -> None:
        """Reset all filters to defaults."""
        self.type_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.date_picker.set_preset("this_month")
        self.search_input.clear()
        self.current_page = 1
        self.load_documents()

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------

    def load_documents(self) -> None:
        """Load documents from service with current filters."""
        type_map = {0: None, 1: "SALE", 2: "PURCHASE", 3: "PROFORMA"}
        status_map = {
            0: None,
            1: "COMPLETED",
            2: "VOID",
            3: "DRAFT",
            4: "QUOTE",
            5: "EXPIRED",
            6: "CONVERTED",
        }

        doc_type = type_map.get(self.type_combo.currentIndex())
        status = status_map.get(self.status_combo.currentIndex())

        from_date = self.from_date.date().toPyDate()
        to_date = self.to_date.date().toPyDate()

        search = self.search_input.text().strip() or None

        result = DocumentBrowserService.search_documents(
            doc_type=doc_type,
            status=status,
            date_from=datetime.combine(from_date, datetime.min.time()),
            date_to=datetime.combine(to_date, datetime.max.time()),
            search_term=search,
            page=self.current_page,
            per_page=50,
        )

        self.total_docs = result["total"]
        self.populate_table(result["documents"])
        self.update_pagination()

    def populate_table(self, documents: list) -> None:
        """Populate the document table."""
        with batch_table_update(self.doc_table):
            self.doc_table.setRowCount(0)
            self.current_doc = None
            self.reset_action_buttons()
            self._hide_detail_panel()

            # Hoist LEGB locals
            table = self.doc_table
            insert_row = table.insertRow
            set_item = table.setItem
            TableItem = QTableWidgetItem
            RelTimeItem = RelativeTimeTableWidgetItem
            user_role = Qt.ItemDataRole.UserRole
            user_role_plus_1 = Qt.ItemDataRole.UserRole + 1
            align_right_vc = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            type_display = {
                "SALE": _t("document_browser.type_sale_display"),
                "PURCHASE": _t("document_browser.type_purchase_display"),
                "PROFORMA": _t("document_browser.type_quotation_display"),
            }
            fmt_curr = format_currency
            fmt_status = format_document_status
            meanings = self.STATUS_MEANINGS
            pill_setter = set_status_pill

            sale_ids = [d["id"] for d in documents if d.get("type", "").upper() == "SALE"]
            self._refund_states = RefundService.refund_states(sale_ids) if sale_ids else {}

            for row, doc in enumerate(documents):
                insert_row(row)

                dt_item = RelTimeItem(doc["date"])
                dt_item.setData(user_role, doc["id"])
                dt_item.setData(user_role_plus_1, doc["type"])
                set_item(row, 0, dt_item)

                set_item(row, 1, TableItem(doc["document_number"]))

                set_item(row, 2, TableItem(type_display.get(doc["type"], doc["type"])))

                set_item(row, 3, TableItem(doc.get("entity_name", "")))

                total = doc.get("total_amount")
                total_text = fmt_curr(total) if total is not None else ""
                total_item = TableItem(total_text)
                total_item.setTextAlignment(align_right_vc)
                set_item(row, 4, total_item)

                status_item = TableItem()
                status_item.setData(user_role, doc["status"])
                doc_type_upper = doc.get("type", "").upper()
                rstate = self._refund_states.get(doc["id"], "NONE") if doc_type_upper == "SALE" else "NONE"
                is_refund_doc = doc_type_upper == "SALE" and (
                    bool(doc.get("refund_of_sale_id"))
                    or doc.get("payment_method") == "REFUND"
                    or doc.get("document_number", "").startswith("CN-")
                )

                if doc["status"] == DocumentStatus.VOID:
                    pill_setter(status_item, fmt_status(doc["status"]), "danger")
                elif is_refund_doc:
                    pill_setter(status_item, fmt_status(doc["status"]), "warning")
                elif rstate == "FULL":
                    pill_setter(status_item, _t("history.pill_refunded"), "info")
                elif rstate == "PARTIAL":
                    pill_setter(status_item, _t("history.pill_part_refunded"), "info")
                else:
                    pill_setter(status_item, fmt_status(doc["status"]), meanings.get(doc["status"]))
                set_item(row, 5, status_item)

                set_item(row, 6, TableItem(doc.get("username", "")))

    def on_selection_changed(self) -> None:
        """Handle row selection — load full details in the panel below."""
        selected = self.doc_table.selectedItems()
        if not selected:
            self.current_doc = None
            self.reset_action_buttons()
            return

        row = selected[0].row()
        first_item = self.doc_table.item(row, 0)
        doc_id = first_item.data(Qt.ItemDataRole.UserRole)
        doc_type = first_item.data(Qt.ItemDataRole.UserRole + 1)

        details = DocumentBrowserService.get_document_details(doc_id, doc_type)
        if details:
            self.current_doc = details
            self.display_details(details)
            self.update_action_buttons(details)
            self._show_detail()

    def _status_badge_html(self, status: str, doc: dict | None = None) -> str:
        """The status as a tinted, bold badge for the rich-text detail panel (#560, #582, #915)."""
        meaning = self.STATUS_MEANINGS.get(status)
        display_text = format_document_status(status)

        if doc and doc.get("type", "").upper() == "SALE":
            rstate = getattr(self, "_refund_states", {}).get(doc.get("id"))
            if rstate is None and doc.get("id"):
                rstate = RefundService.refund_state(doc.get("id"))
            if rstate == "FULL":
                display_text = _t("history.pill_refunded")
                meaning = INFO
            elif rstate == "PARTIAL":
                display_text = _t("history.pill_part_refunded")
                meaning = INFO

        if not meaning:
            return display_text
        fg, fill = pill_colors(meaning)
        return (
            f'<span style="background-color:{fill.name()}; color:{fg.name()}; font-weight:bold;">'
            f"&nbsp;{display_text}&nbsp;</span>"
        )

    def _summary_html(self, doc: dict) -> str:
        """The summary as a two-column table (#612): who/when first, then money, right-aligned."""

        def row(label: str, value: str, money: bool = False, bold: bool = False) -> str:
            value = f"<b>{value}</b>" if bold else value
            align = ' align="right"' if money else ""
            return (
                f'<tr><td style="padding:2px 16px 2px 0;">{html.escape(label)}</td>'
                f'<td{align} style="padding:2px 0;">{value}</td></tr>'
            )

        if doc.get("date"):
            exact_d = format_datetime(doc["date"])
            rel_d = format_relative_time(doc["date"])
            date_display = f"{rel_d} ({exact_d})"
        else:
            date_display = _t("common.na")

        meta = [
            row(_t("document_browser.detail_date"), date_display),
            row(_t("document_browser.detail_status"), self._status_badge_html(doc["status"], doc)),
            row(_t("document_browser.detail_user"), html.escape(doc.get("username") or "")),
        ]

        entity = doc.get("entity_name", "")
        if entity:
            label = (
                _t("document_browser.detail_supplier")
                if doc["type"] == "purchase"
                else _t("document_browser.detail_customer")
            )
            meta.append(row(label, html.escape(entity)))
        if doc.get("refund_of_sale_id"):
            meta.append(row(_t("document_browser.detail_refund_of_sale"), f"#{doc['refund_of_sale_id']}"))
        if doc["type"] == "proforma":
            if doc.get("validity_days"):
                meta.append(
                    row(
                        _t("document_browser.detail_validity"),
                        f"{doc['validity_days']} {_t('document_browser.detail_days')}",
                    )
                )
            if doc.get("expiry_date"):
                meta.append(row(_t("document_browser.detail_expiry"), html.escape(str(doc["expiry_date"]))))
            if doc.get("converted_sale_id"):
                meta.append(row(_t("document_browser.detail_converted_to_sale"), f"#{doc['converted_sale_id']}"))
            if doc.get("notes"):
                meta.append(row(_t("document_browser.detail_notes"), html.escape(doc["notes"])))

        money = []
        total = doc.get("total_amount")
        if total is not None:
            money.append(row(_t("document_browser.detail_total"), format_currency(total), money=True, bold=True))
        if doc["type"] == "sale" and (TaxService.is_vat_active() or doc.get("tax_vat", 0) > 0):
            for key, field in (
                ("detail_vat", "tax_vat"),
                ("detail_sscl", "tax_sscl"),
                ("detail_net_revenue", "net_revenue"),
            ):
                if doc.get(field) is not None:
                    money.append(row(_t(f"document_browser.{key}"), format_currency(doc[field]), money=True))

        gap = '<tr><td colspan="2" style="font-size:6px;">&nbsp;</td></tr>' if money else ""
        return f'<table width="100%" cellspacing="0" cellpadding="0">{"".join(meta)}{gap}{"".join(money)}</table>'

    def _fit_items_table(self) -> None:
        """Grow the line-items table to show its rows (up to ITEMS_FIT_MAX_ROWS), so the
        panel scrolls as one instead of a small table scrolling inside it."""
        table = self.items_table
        rows = min(max(table.rowCount(), 1), self.ITEMS_FIT_MAX_ROWS)
        row_h = table.rowHeight(0) if table.rowCount() else table.verticalHeader().defaultSectionSize()
        height = table.horizontalHeader().sizeHint().height() + rows * row_h + 2 * table.frameWidth() + 4
        table.setMinimumHeight(max(self.ITEMS_MIN_HEIGHT, height))

    def display_details(self, doc: dict) -> None:
        """Display document details in the detail panel."""
        type_labels = {
            "sale": _t("document_browser.type_sale_display"),
            "purchase": _t("document_browser.type_purchase_display"),
            "proforma": _t("document_browser.type_quotation_display"),
        }

        self.detail_title.setText(f"{type_labels.get(doc['type'], doc['type'])} — {doc['document_number']}")

        self.details_label.setText(self._summary_html(doc))

        # Populate line items
        items = doc.get("items", [])
        with batch_table_update(self.items_table):
            self.items_table.setRowCount(0)

            # Hoist LEGB locals
            table = self.items_table
            insert_row = table.insertRow
            set_item = table.setItem
            TableItem = QTableWidgetItem
            align_right_vc = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            fmt_qty = format_quantity
            fmt_curr = format_currency
            fmt_disc = format_discount

            for idx, item in enumerate(items):
                insert_row(idx)
                product_name = item.get("product_name", "")
                note = item.get("notes")
                name_item = TableItem(f"\U0001f4dd {product_name}" if note else product_name)
                if note:
                    name_item.setToolTip(note)
                set_item(idx, 0, name_item)

                qty_item = TableItem(fmt_qty(item["quantity"]))
                qty_item.setTextAlignment(align_right_vc)
                set_item(idx, 1, qty_item)

                price_item = TableItem(fmt_curr(item["unit_price"]))
                price_item.setTextAlignment(align_right_vc)
                set_item(idx, 2, price_item)

                disc_text = fmt_disc(item.get("discount_type"), item.get("discount_value"))
                disc_item = TableItem(disc_text)
                disc_item.setTextAlignment(align_right_vc)
                set_item(idx, 3, disc_item)

                total_item = TableItem(fmt_curr(item["line_total"]))
                total_item.setTextAlignment(align_right_vc)
                set_item(idx, 4, total_item)

        # Most documents have no line discounts: drop the empty column so the
        # amounts fit the side panel without scrolling sideways.
        has_discount = any(self.items_table.item(r, 3).text() for r in range(self.items_table.rowCount()))
        self.items_table.setColumnHidden(3, not has_discount)
        self._fit_items_table()

        # Payment info
        payments = doc.get("payments", [])
        if payments:
            pay_lines = []
            for p in payments:
                pay_lines.append(f"{format_payment_method(p['method'])}: {format_currency(p['amount'])}")
            self.payment_label.setText(f"<b>{_t('document_browser.detail_payments')}:</b> " + " | ".join(pay_lines))
        else:
            self.payment_label.setText("")

    # ------------------------------------------------------------------
    # Action Buttons
    # ------------------------------------------------------------------

    def reset_action_buttons(self) -> None:
        """Disable all action buttons."""
        for btn in self._action_buttons:
            btn.setEnabled(False)
        self._layout_action_buttons()

    def _layout_action_buttons(self) -> None:
        """Show only the actions that apply (enabled), packed two per row with no gaps."""
        while self._action_grid.count():
            self._action_grid.takeAt(0)
        shown = [btn for btn in self._action_buttons if btn.isEnabled()]
        for i, btn in enumerate(shown):
            self._action_grid.addWidget(btn, i // 2, i % 2)
        for btn in self._action_buttons:
            btn.setVisible(btn in shown)

    def update_action_buttons(self, doc: dict) -> None:
        """Enable relevant action buttons based on document type and status."""
        doc_type = doc.get("type", "").lower()
        status = doc.get("status", "")
        doc_id = doc.get("id")

        rstate = getattr(self, "_refund_states", {}).get(doc_id) if doc_type == "sale" else "NONE"
        if doc_type == "sale" and rstate is None and doc_id:
            rstate = RefundService.refund_state(doc_id)

        is_refund_doc = doc_type == "sale" and (
            bool(doc.get("refund_of_sale_id"))
            or doc.get("payment_method") == "REFUND"
            or doc.get("document_number", "").startswith("CN-")
        )

        self.reprint_btn.setEnabled(doc_type in ("sale", "purchase", "proforma") and status != DocumentStatus.VOID)
        if status == DocumentStatus.VOID:
            self.reprint_btn.setToolTip(_t("reprint.void_blocked"))
        else:
            self.reprint_btn.setToolTip("")

        is_refundable = (
            doc_type == "sale" and status == DocumentStatus.COMPLETED and not is_refund_doc and rstate != "FULL"
        )
        self.refund_btn.setEnabled(is_refundable)
        if doc_type == "sale" and rstate == "FULL":
            self.refund_btn.setToolTip(_t("history.refund_disabled_full"))
        elif is_refund_doc:
            self.refund_btn.setToolTip(_t("history.void_disabled_is_refund"))
        else:
            self.refund_btn.setToolTip("")

        self.convert_btn.setEnabled(doc_type == "proforma" and status == DocumentStatus.QUOTE)

        can_void = (
            status
            not in (
                DocumentStatus.VOID,
                DocumentStatus.CONVERTED,
                DocumentStatus.EXPIRED,
            )
            and not is_refund_doc
            and rstate == "NONE"
        )
        self.void_btn.setEnabled(can_void)
        if is_refund_doc:
            self.void_btn.setToolTip(_t("history.void_disabled_is_refund"))
        elif doc_type == "sale" and rstate != "NONE":
            self.void_btn.setToolTip(_t("history.void_disabled_refunded"))
        else:
            self.void_btn.setToolTip("")

        self.transfer_btn.setEnabled(doc_type == "sale" and status == DocumentStatus.COMPLETED)
        self._layout_action_buttons()

    def reprint_document(self) -> None:
        """Reprint the selected document."""
        if not self.current_doc:
            return

        doc_type = self.current_doc.get("type", "")

        try:
            if hasattr(self, "reprint_btn"):
                self.reprint_btn.setEnabled(False)
            if doc_type == "sale":
                from cbpos.core.constants.permissions import Permissions
                from cbpos.core.services.auth_service import AuthService
                from cbpos.core.services.receipt_reprint_service import ReceiptReprintService
                from cbpos.core.utils.permission_helper import check_permission_with_override

                authorized_user = check_permission_with_override(Permissions.SALES_REPRINT, self)
                if not authorized_user:
                    if hasattr(self, "reprint_btn"):
                        self.reprint_btn.setEnabled(True)
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

                job = ReceiptReprintService.reprint(
                    self.current_doc["id"],
                    user_id=user_id,
                    approver_id=approver_id,
                )
                worker = self._connect_print_signals()
                worker.add_job("print_receipt", job.commands)
            elif doc_type == "proforma":
                from cbpos.core.services.receipt_builder import ReceiptBuilder

                proforma = ProformaService.get_proforma_details(self.current_doc["id"])
                if proforma:
                    commands = ReceiptBuilder.build_proforma(proforma)
                    worker = self._connect_print_signals()
                    worker.add_job("print_commands", commands)
                else:
                    if hasattr(self, "reprint_btn"):
                        self.reprint_btn.setEnabled(True)
            else:
                if hasattr(self, "reprint_btn"):
                    self.reprint_btn.setEnabled(True)
                QMessageBox.information(
                    self,
                    _t("document_browser.info_title"),
                    _t("document_browser.reprint_not_supported"),
                )

        except Exception as e:
            if hasattr(self, "reprint_btn"):
                self.reprint_btn.setEnabled(True)
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("document_browser.reprint_failed"),
            )
            logger.error("Reprint failed: %s", e)

    def _connect_print_signals(self) -> PrintWorker:
        """Return the shared PrintWorker, connected to report the real
        outcome of the job about to be queued.

        PrintWorker.add_job() only queues the job -- the print itself
        happens later, asynchronously, on the worker thread. Showing
        "success" right after add_job() (the old behavior) meant the
        user was told the reprint worked even when the printer wasn't
        configured at all. Guard against reconnecting on every call the
        same way ReceiptOptionsDialog.print_thermal() does.
        """
        worker = PrintWorker.instance()
        self._print_worker = worker
        try:
            worker.error_occurred.disconnect(self._on_reprint_error)
        except TypeError as e:
            logger.debug("Signal not connected yet: %s", e)
        with contextlib.suppress(TypeError):
            worker.job_completed.disconnect(self._on_reprint_finished)
        worker.error_occurred.connect(self._on_reprint_error)
        worker.job_completed.connect(self._on_reprint_finished)
        return worker

    def _on_reprint_finished(self) -> None:
        """Called once the queued print job actually completes."""
        if hasattr(self, "reprint_btn"):
            self.reprint_btn.setEnabled(True)
        doc_type = self.current_doc.get("type", "") if self.current_doc else ""
        key = "receipt_sent_to_printer" if doc_type == "sale" else "quotation_sent_to_printer"
        doc_num = self.current_doc.get("document_number", "") if self.current_doc else ""
        QMessageBox.information(
            self,
            _t("common.success"),
            _t(f"document_browser.{key}", doc_number=doc_num),
        )

    def _on_reprint_error(self, message: str) -> None:
        """Called if the queued print job actually fails (e.g. no printer configured)."""
        if hasattr(self, "reprint_btn"):
            self.reprint_btn.setEnabled(True)
        logger.error("Reprint failed: %s", message)
        QMessageBox.critical(self, _t("common.error"), _t("document_browser.reprint_failed"))

    def process_refund(self) -> None:
        """Process a refund for the selected sale by opening the shared RefundDialog."""
        if not self.current_doc or self.current_doc.get("type") != "sale":
            return

        from cbpos.ui.dialogs.refund_dialog import RefundDialog

        sale = SaleQueryService.get_sale_details(self.current_doc["id"])
        if not sale:
            QMessageBox.critical(self, _t("common.error"), _t("document_browser.refund_failed"))
            return

        dlg = RefundDialog(self)
        dlg.load_sale(sale)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_documents()

    def convert_proforma(self) -> None:
        """Convert selected proforma to a sale via SalesView."""
        if not self.current_doc or self.current_doc.get("type") != "proforma":
            return

        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        user = check_permission_with_override(Permissions.DOCUMENTS_CONVERT_PROFORMA, self)
        if not user:
            return

        reply = QMessageBox.question(
            self,
            _t("document_browser.convert_title"),
            _t(
                "document_browser.convert_question",
                doc_number=self.current_doc["document_number"],
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            cart_data = ProformaService.convert_to_sale(self.current_doc["id"])
            if cart_data:
                self.convert_to_sale_requested.emit(cart_data)
            else:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("document_browser.convert_failed"),
                )

    def void_document(self) -> None:
        """Void the selected document."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.DOCUMENTS_VOID, self):
            return

        if not self.current_doc:
            return

        doc_type = self.current_doc.get("type", "")
        doc_number = self.current_doc.get("document_number", "")

        dialog = VoidReasonDialog(
            TransactionService.get_void_reasons(),
            bool(ConfigService.get("require_void_reason")),
            doc_number,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            if doc_type == "proforma":
                success = ProformaService.void_proforma(self.current_doc["id"], dialog.reason_id)
            elif doc_type == "sale":
                current_user = AuthService.get_current_user()
                if not current_user:
                    QMessageBox.warning(self, _t("common.error"), _t("document_browser.no_user_msg"))
                    return
                success = TransactionService.void_sale(
                    self.current_doc["id"], current_user.id, dialog.reason_text, reason_id=dialog.reason_id
                )
            else:
                QMessageBox.information(
                    self,
                    _t("document_browser.info_title"),
                    _t("document_browser.void_not_supported"),
                )
                return

            if success:
                QMessageBox.information(
                    self,
                    _t("common.success"),
                    _t("document_browser.void_success", doc_number=doc_number),
                )
                self.load_documents()
            else:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("document_browser.void_failed"),
                )
        except Exception as e:
            logger.exception("Void failed: %s", e)
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("document_browser.void_error", error=translate_error(str(e))),
            )

    def transfer_order(self) -> None:
        """Reassign the selected sale's cashier-of-record to another user (#479)."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.services.user_service import UserService
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.DOCUMENTS_TRANSFER, self):
            return

        if not self.current_doc or self.current_doc.get("type") != "sale":
            return

        current_username = self.current_doc.get("username", "")
        candidates = [u for u in UserService.get_all_users() if u.is_active and u.username != current_username]

        if not candidates:
            QMessageBox.information(
                self, _t("document_browser.info_title"), _t("document_browser.transfer_no_other_users")
            )
            return

        usernames = [u.username for u in candidates]
        choice, ok = QInputDialog.getItem(
            self,
            _t("document_browser.transfer_title"),
            _t("document_browser.transfer_prompt"),
            usernames,
            0,
            False,
        )
        if not ok or not choice:
            return

        target_user = next(u for u in candidates if u.username == choice)
        doc_number = self.current_doc.get("document_number", "")

        try:
            success = TransactionService.transfer_order(self.current_doc["id"], target_user.id)
            if success:
                QMessageBox.information(
                    self,
                    _t("common.success"),
                    _t("document_browser.transfer_success", doc_number=doc_number, user=target_user.username),
                )
                self.load_documents()
            else:
                QMessageBox.critical(self, _t("common.error"), _t("document_browser.transfer_failed"))
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), _t("document_browser.transfer_failed"))
            logger.error("Transfer order failed: %s", e)

    def open_proforma_dialog(self) -> None:
        """Open the dialog to create a new proforma/quotation."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.ui.dialogs.proforma_dialog import ProformaDialog

        user = check_permission_with_override(Permissions.DOCUMENTS_CREATE_PROFORMA, self)
        if not user:
            return

        dialog = ProformaDialog(self)
        if dialog.exec():
            self.load_documents()

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def update_pagination(self) -> None:
        """Update pagination controls."""
        total_pages = max(1, (self.total_docs + 49) // 50)
        self.page_label.setText(
            _t(
                "document_browser.page_info",
                current=self.current_page,
                total_pages=total_pages,
                total_docs=self.total_docs,
            )
        )
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < total_pages)

    def prev_page(self) -> None:
        """Go to the previous page of documents, if not already on the first."""
        if self.current_page > 1:
            self.current_page -= 1
            self.load_documents()

    def next_page(self) -> None:
        """Go to the next page of documents, if not already on the last."""
        total_pages = max(1, (self.total_docs + 49) // 50)
        if self.current_page < total_pages:
            self.current_page += 1
            self.load_documents()

    def on_activated(self) -> None:
        """Reload when this view is shown again, so the user never sees stale data."""
        self.load_documents()
