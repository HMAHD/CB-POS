import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDateEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QComboBox,
    QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QColor

from cbpos.core.services.document_browser_service import DocumentBrowserService
from cbpos.core.services.proforma_service import ProformaService
from cbpos.core.services.receipt_service import ReceiptService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.constants.status import DocumentStatus
from cbpos.core.utils.formatters import format_currency
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.core.services.tax_service import TaxService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.widgets.table_helpers import configure_table_columns

logger = logging.getLogger(__name__)


class DocumentBrowserView(QWidget):
    """
    Unified document browser with full-width table and expandable detail panel.
    No splitter — details appear below the table when a document is selected.
    """

    convert_to_sale_requested = pyqtSignal(dict)

    STATUS_COLORS = {
        "COMPLETED": QColor("#39FF14"),
        "VOID": QColor("#FF4136"),
        "QUOTE": QColor("#00BCEB"),
        "EXPIRED": QColor("#888888"),
        "CONVERTED": QColor("#FF851B"),
        "DRAFT": QColor("#FFDC00"),
        "SUSPENDED": QColor("#FFDC00"),
    }

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DocumentBrowserView")
        self.current_doc: dict | None = None
        self.current_page = 1
        self.total_docs = 0
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))
        try:
            self.load_documents()
        except Exception as e:
            logger.error("Failed to load documents on init: %s", e)

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title row
        title_row = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("DocBrowserTitle")
        title_row.addWidget(self.title_label)
        title_row.addStretch()

        self.new_proforma_btn = QPushButton()
        self.new_proforma_btn.setObjectName("DocNewQuotationBtn")
        self.new_proforma_btn.clicked.connect(self.open_proforma_dialog)
        title_row.addWidget(self.new_proforma_btn)
        layout.addLayout(title_row)

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

        self.lbl_from = QLabel()
        self.lbl_from.setObjectName("DocFilterLabel")
        filter_layout.addWidget(self.lbl_from)
        self.from_date = QDateEdit()
        self.from_date.setObjectName("DocDateEdit")
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.from_date)

        self.lbl_to = QLabel()
        self.lbl_to.setObjectName("DocFilterLabel")
        filter_layout.addWidget(self.lbl_to)
        self.to_date = QDateEdit()
        self.to_date.setObjectName("DocDateEdit")
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self.to_date)

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
        )
        self.doc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.doc_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.doc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.doc_table.verticalHeader().setVisible(False)
        self.doc_table.setAlternatingRowColors(True)
        self.doc_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.doc_table.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.doc_table, 3)

        # Detail Panel (below table, initially hidden)
        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("DocDetailPanel")
        self.detail_panel.setVisible(False)
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(12, 10, 12, 10)
        detail_layout.setSpacing(8)

        # Detail header row
        detail_header = QHBoxLayout()
        self.detail_title = QLabel()
        self.detail_title.setObjectName("DocDetailTitle")
        detail_header.addWidget(self.detail_title)
        detail_header.addStretch()

        self.btn_close_detail = QPushButton()
        self.btn_close_detail.setObjectName("DocDetailCloseBtn")
        self.btn_close_detail.clicked.connect(self._close_detail)
        detail_header.addWidget(self.btn_close_detail)
        detail_layout.addLayout(detail_header)

        # Detail content: info + items side by side
        detail_content = QHBoxLayout()
        detail_content.setSpacing(16)

        # Left: document info
        info_frame = QFrame()
        info_frame.setObjectName("DocInfoFrame")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(0, 0, 0, 0)
        self.details_label = QLabel()
        self.details_label.setObjectName("DocInfoLabel")
        self.details_label.setWordWrap(True)
        info_layout.addWidget(self.details_label)

        self.payment_label = QLabel("")
        self.payment_label.setObjectName("DocPaymentLabel")
        self.payment_label.setWordWrap(True)
        info_layout.addWidget(self.payment_label)
        info_layout.addStretch()
        detail_content.addWidget(info_frame, 1)

        # Right: line items table
        items_frame = QWidget()
        items_layout = QVBoxLayout(items_frame)
        items_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_items_title = QLabel()
        self.lbl_items_title.setObjectName("DocItemsTitle")
        items_layout.addWidget(self.lbl_items_title)

        self.items_table = QTableWidget()
        self.items_table.setObjectName("DocItemsTable")
        self.items_table.setColumnCount(5)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.setMaximumHeight(200)
        items_layout.addWidget(self.items_table)
        detail_content.addWidget(items_frame, 2)

        detail_layout.addLayout(detail_content)

        # Action buttons row
        action_row = QHBoxLayout()
        action_row.addStretch()

        self.reprint_btn = QPushButton()
        self.reprint_btn.setObjectName("DocReprintBtn")
        self.reprint_btn.clicked.connect(self.reprint_document)
        self.reprint_btn.setEnabled(False)
        action_row.addWidget(self.reprint_btn)

        self.convert_btn = QPushButton()
        self.convert_btn.setObjectName("DocConvertBtn")
        self.convert_btn.clicked.connect(self.convert_proforma)
        self.convert_btn.setEnabled(False)
        action_row.addWidget(self.convert_btn)

        self.refund_btn = QPushButton()
        self.refund_btn.setObjectName("DocRefundBtn")
        self.refund_btn.clicked.connect(self.process_refund)
        self.refund_btn.setEnabled(False)
        action_row.addWidget(self.refund_btn)

        self.void_btn = QPushButton()
        self.void_btn.setObjectName("DocVoidBtn")
        self.void_btn.clicked.connect(self.void_document)
        self.void_btn.setEnabled(False)
        action_row.addWidget(self.void_btn)

        detail_layout.addLayout(action_row)
        layout.addWidget(self.detail_panel, 2)

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

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.title_label.setText(_t("document_browser.title"))
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

        # Action buttons
        self.reprint_btn.setText(_t("document_browser.btn_reprint"))
        self.convert_btn.setText(_t("document_browser.btn_convert_to_sale"))
        self.refund_btn.setText(_t("document_browser.btn_refund"))
        self.void_btn.setText(_t("document_browser.btn_void"))

        # Pagination
        self.prev_btn.setText(_t("document_browser.btn_previous"))
        self.next_btn.setText(_t("document_browser.btn_next"))

    # ------------------------------------------------------------------
    # Detail Panel
    # ------------------------------------------------------------------

    def _close_detail(self) -> None:
        """Hide the detail panel."""
        self.detail_panel.setVisible(False)
        self.current_doc = None
        self.reset_action_buttons()

    def _show_detail(self) -> None:
        """Show the detail panel."""
        self.detail_panel.setVisible(True)

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
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date.setDate(QDate.currentDate())
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
        self.doc_table.setRowCount(0)
        self.current_doc = None
        self.reset_action_buttons()
        self.detail_panel.setVisible(False)

        for row, doc in enumerate(documents):
            self.doc_table.insertRow(row)

            dt_item = QTableWidgetItem(doc["date"].strftime("%Y-%m-%d %H:%M") if doc["date"] else "")
            dt_item.setData(Qt.ItemDataRole.UserRole, doc["id"])
            dt_item.setData(Qt.ItemDataRole.UserRole + 1, doc["type"])
            self.doc_table.setItem(row, 0, dt_item)

            self.doc_table.setItem(row, 1, QTableWidgetItem(doc["document_number"]))

            type_display = {
                "SALE": _t("document_browser.type_sale_display"),
                "PURCHASE": _t("document_browser.type_purchase_display"),
                "PROFORMA": _t("document_browser.type_quotation_display"),
            }
            self.doc_table.setItem(row, 2, QTableWidgetItem(type_display.get(doc["type"], doc["type"])))

            self.doc_table.setItem(row, 3, QTableWidgetItem(doc.get("entity_name", "")))

            total = doc.get("total_amount")
            total_text = format_currency(total) if total is not None else ""
            total_item = QTableWidgetItem(total_text)
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.doc_table.setItem(row, 4, total_item)

            status_item = QTableWidgetItem(doc["status"])
            color = self.STATUS_COLORS.get(doc["status"])
            if color:
                status_item.setForeground(color)
            self.doc_table.setItem(row, 5, status_item)

            self.doc_table.setItem(row, 6, QTableWidgetItem(doc.get("username", "")))

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

    def display_details(self, doc: dict) -> None:
        """Display document details in the detail panel."""
        type_labels = {
            "sale": _t("document_browser.type_sale_display"),
            "purchase": _t("document_browser.type_purchase_display"),
            "proforma": _t("document_browser.type_quotation_display"),
        }

        self.detail_title.setText(f"{type_labels.get(doc['type'], doc['type'])} — {doc['document_number']}")

        html = (
            f"<b>{_t('document_browser.detail_date')}:</b> "  # noqa: E231
            f"{doc['date'].strftime('%Y-%m-%d %H:%M:%S') if doc['date'] else 'N/A'}<br>"
            f"<b>{_t('document_browser.detail_status')}:</b> {doc['status']}<br>"  # noqa: E231
            f"<b>{_t('document_browser.detail_user')}:</b> {doc.get('username', '')}<br>"  # noqa: E231
        )

        entity = doc.get("entity_name", "")
        if entity:
            label = (
                _t("document_browser.detail_supplier")
                if doc["type"] == "purchase"
                else _t("document_browser.detail_customer")
            )
            html += f"<b>{label}:</b> {entity}<br>"  # noqa: E231

        total = doc.get("total_amount")
        if total is not None:
            html += f"<b>{_t('document_browser.detail_total')}:</b> {format_currency(total)}<br>"  # noqa: E231

        if doc["type"] == "sale" and (TaxService.is_vat_active() or doc.get("tax_vat", 0) > 0):
            tax_vat = doc.get("tax_vat")
            if tax_vat is not None:
                html += f"<b>{_t('document_browser.detail_vat')}:</b> {format_currency(tax_vat)}<br>"  # noqa: E231
            tax_sscl = doc.get("tax_sscl")
            if tax_sscl is not None:
                html += f"<b>{_t('document_browser.detail_sscl')}:</b> {format_currency(tax_sscl)}<br>"  # noqa: E231
            net_revenue = doc.get("net_revenue")
            if net_revenue is not None:
                html += (
                    f"<b>{_t('document_browser.detail_net_revenue')}:</b> "  # noqa: E231
                    f"{format_currency(net_revenue)}<br>"
                )

        if doc["type"] == "proforma":
            if doc.get("validity_days"):
                html += (
                    f"<b>{_t('document_browser.detail_validity')}:</b> "  # noqa: E231
                    f"{doc['validity_days']} {_t('document_browser.detail_days')}<br>"
                )
            if doc.get("expiry_date"):
                html += f"<b>{_t('document_browser.detail_expiry')}:</b> {doc['expiry_date']}<br>"  # noqa: E231
            if doc.get("notes"):
                html += f"<b>{_t('document_browser.detail_notes')}:</b> {doc['notes']}<br>"  # noqa: E231
            if doc.get("converted_sale_id"):
                html += (
                    f"<b>{_t('document_browser.detail_converted_to_sale')}:</b> "  # noqa: E231
                    f"#{doc['converted_sale_id']}<br>"
                )

        if doc.get("refund_of_sale_id"):
            html += (
                f"<b>{_t('document_browser.detail_refund_of_sale')}:</b> "  # noqa: E231
                f"#{doc['refund_of_sale_id']}<br>"
            )

        self.details_label.setText(html)

        # Populate line items
        items = doc.get("items", [])
        self.items_table.setRowCount(0)
        for idx, item in enumerate(items):
            self.items_table.insertRow(idx)
            self.items_table.setItem(idx, 0, QTableWidgetItem(item.get("product_name", "")))

            qty_item = QTableWidgetItem(f"{item['quantity']:.3f}")  # noqa: E231
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(idx, 1, qty_item)

            price_item = QTableWidgetItem(format_currency(item["unit_price"]))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(idx, 2, price_item)

            disc = item.get("discount_type", "NONE")
            disc_val = item.get("discount_value", 0)
            disc_text = "" if disc == "NONE" else f"{disc} {disc_val}"
            self.items_table.setItem(idx, 3, QTableWidgetItem(disc_text))

            total_item = QTableWidgetItem(format_currency(item["line_total"]))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(idx, 4, total_item)

        # Payment info
        payments = doc.get("payments", [])
        if payments:
            pay_lines = []
            for p in payments:
                pay_lines.append(f"{p['method']}: {format_currency(p['amount'])}")
            self.payment_label.setText(
                f"<b>{_t('document_browser.detail_payments')}:</b> " + " | ".join(pay_lines)  # noqa: E231
            )
        else:
            self.payment_label.setText("")

    # ------------------------------------------------------------------
    # Action Buttons
    # ------------------------------------------------------------------

    def reset_action_buttons(self) -> None:
        """Disable all action buttons."""
        self.reprint_btn.setEnabled(False)
        self.refund_btn.setEnabled(False)
        self.convert_btn.setEnabled(False)
        self.void_btn.setEnabled(False)

    def update_action_buttons(self, doc: dict) -> None:
        """Enable relevant action buttons based on document type and status."""
        doc_type = doc.get("type", "")
        status = doc.get("status", "")

        self.reprint_btn.setEnabled(doc_type in ("sale", "purchase", "proforma") and status != DocumentStatus.VOID)

        is_refundable = doc_type == "sale" and status == DocumentStatus.COMPLETED and not doc.get("refund_of_sale_id")
        self.refund_btn.setEnabled(is_refundable)

        self.convert_btn.setEnabled(doc_type == "proforma" and status == DocumentStatus.QUOTE)

        self.void_btn.setEnabled(
            status
            not in (
                DocumentStatus.VOID,
                DocumentStatus.CONVERTED,
                DocumentStatus.EXPIRED,
            )
        )

    def reprint_document(self) -> None:
        """Reprint the selected document."""
        if not self.current_doc:
            return

        doc_type = self.current_doc.get("type", "")

        try:
            if doc_type == "sale":
                sale = SaleQueryService.get_sale_details(self.current_doc["id"])
                if sale:
                    from cbpos.core.services.config_service import ConfigService

                    settings = ConfigService.get_all()
                    language = settings.get("language", "en")
                    worker = self._connect_print_signals()

                    if language == "en":
                        receipt_text = ReceiptService.build_receipt_text(sale)
                        worker.add_job("print_receipt", receipt_text)
                    else:
                        receipt_image = ReceiptService.build_receipt_image(sale)
                        worker.add_job("print_image", receipt_image)
            elif doc_type == "proforma":
                from cbpos.core.services.receipt_builder import ReceiptBuilder

                proforma = ProformaService.get_proforma_details(self.current_doc["id"])
                if proforma:
                    commands = ReceiptBuilder.build_proforma(proforma)
                    worker = self._connect_print_signals()
                    worker.add_job("print_commands", commands)
            else:
                QMessageBox.information(
                    self,
                    _t("document_browser.info_title"),
                    _t("document_browser.reprint_not_supported"),
                )

        except Exception as e:
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
        try:
            worker.error_occurred.disconnect(self._on_reprint_error)
        except TypeError:
            pass  # not connected yet
        try:
            worker.job_completed.disconnect(self._on_reprint_finished)
        except TypeError:
            pass
        worker.error_occurred.connect(self._on_reprint_error)
        worker.job_completed.connect(self._on_reprint_finished)
        return worker

    def _on_reprint_finished(self) -> None:
        """Called once the queued print job actually completes."""
        doc_type = self.current_doc.get("type", "")
        key = "receipt_sent_to_printer" if doc_type == "sale" else "quotation_sent_to_printer"
        QMessageBox.information(
            self,
            _t("common.success"),
            _t(f"document_browser.{key}", doc_number=self.current_doc["document_number"]),
        )

    def _on_reprint_error(self, message: str) -> None:
        """Called if the queued print job actually fails (e.g. no printer configured)."""
        logger.error("Reprint failed: %s", message)
        QMessageBox.critical(self, _t("common.error"), _t("document_browser.reprint_failed"))

    def process_refund(self) -> None:
        """Process a refund for the selected sale."""
        if not self.current_doc or self.current_doc.get("type") != "sale":
            return

        reply = QMessageBox.question(
            self,
            _t("document_browser.confirm_refund_title"),
            f"<b>{_t('document_browser.refund_question')}</b><br><br>"
            f"{_t('document_browser.detail_receipt')}: {self.current_doc['document_number']}<br>"
            f"{_t('common.amount')}: {format_currency(self.current_doc['total_amount'])}<br><br>"
            f"<b style='color: #FF4136'>{_t('common.warning')}:</b> "  # noqa: E231
            f"{_t('document_browser.refund_warning')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                current_user = AuthService.get_current_user()
                if not current_user:
                    QMessageBox.warning(self, _t("common.error"), _t("document_browser.no_user_msg"))
                    return

                success = TransactionService.process_refund(self.current_doc["id"], "Customer Return", current_user.id)
                if success:
                    QMessageBox.information(
                        self,
                        _t("common.success"),
                        _t("document_browser.refund_success"),
                    )
                    self.load_documents()
                else:
                    QMessageBox.critical(
                        self,
                        _t("common.error"),
                        _t("document_browser.refund_failed"),
                    )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("document_browser.refund_error", error=str(e)),
                )

    def convert_proforma(self) -> None:
        """Convert selected proforma to a sale via SalesView."""
        if not self.current_doc or self.current_doc.get("type") != "proforma":
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
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.DOCUMENTS_VOID, self):
            return

        if not self.current_doc:
            return

        doc_type = self.current_doc.get("type", "")
        doc_number = self.current_doc.get("document_number", "")

        reply = QMessageBox.question(
            self,
            _t("document_browser.confirm_void_title"),
            f"<b>{_t('document_browser.void_question', doc_number=doc_number)}</b><br><br>"
            f"<b style='color: #FF4136'>{_t('document_browser.void_warning')}</b>",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if doc_type == "proforma":
                success = ProformaService.void_proforma(self.current_doc["id"])
            elif doc_type == "sale":
                current_user = AuthService.get_current_user()
                if not current_user:
                    QMessageBox.warning(self, _t("common.error"), _t("document_browser.no_user_msg"))
                    return
                success = TransactionService.void_sale(self.current_doc["id"], current_user.id)
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
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("document_browser.void_error", error=str(e)),
            )

    def open_proforma_dialog(self) -> None:
        """Open the dialog to create a new proforma/quotation."""
        from cbpos.ui.dialogs.proforma_dialog import ProformaDialog

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
        if self.current_page > 1:
            self.current_page -= 1
            self.load_documents()

    def next_page(self) -> None:
        total_pages = max(1, (self.total_docs + 49) // 50)
        if self.current_page < total_pages:
            self.current_page += 1
            self.load_documents()
