import contextlib
import logging
from datetime import datetime

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.printer_service import PrinterService
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.formatters import format_currency, format_relative_time
from cbpos.i18n import _t, register_language_callback
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.refund_messages import refund_confirm_html, refund_done_text
from cbpos.ui.resources.status_colors import DANGER, WARNING, status_color
from cbpos.ui.widgets.table_helpers import RelativeTimeTableWidgetItem

logger = logging.getLogger(__name__)


class HistoryView(QWidget):
    """
    Transaction History view with filtering, reprinting, and refund capabilities.
    """

    def __init__(self):
        """Build the UI and load today's transactions."""
        super().__init__()
        self.current_sale = None
        self.init_ui()
        self.load_today()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self):
        """Setup the UI layout"""
        layout = QVBoxLayout(self)

        # Filter Bar
        filter_layout = QHBoxLayout()

        self.from_label = QLabel(_t("common.from"))
        filter_layout.addWidget(self.from_label)
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self.from_date)

        self.to_label = QLabel(_t("common.to"))
        filter_layout.addWidget(self.to_label)
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self.to_date)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_t("history.search_placeholder"))
        filter_layout.addWidget(self.search_input, 1)

        self.filter_btn = QPushButton(_t("common.filter"))
        self.filter_btn.clicked.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_btn)

        layout.addLayout(filter_layout)

        # Main Content: Splitter with table and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Transaction Table
        self.transaction_table = QTableWidget()
        self.transaction_table.setColumnCount(6)
        self.transaction_table.setHorizontalHeaderLabels(
            [
                _t("history.col_datetime"),
                _t("history.col_receipt"),
                _t("history.col_cashier"),
                _t("common.total"),
                _t("history.col_method"),
                _t("common.status"),
            ]
        )
        self.transaction_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.transaction_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.transaction_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.transaction_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.transaction_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.transaction_table.doubleClicked.connect(self.on_double_click)
        splitter.addWidget(self.transaction_table)

        # Details Panel
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)

        self.details_title_label = QLabel(f"<b>{_t('history.transaction_details')}</b>")
        details_layout.addWidget(self.details_title_label)

        self.details_label = QLabel(_t("history.select_transaction"))
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet("padding: 10px; background: #002244;")
        details_layout.addWidget(self.details_label)

        # Line Items Table
        self.line_items_label = QLabel(f"<b>{_t('history.line_items')}:</b>")
        details_layout.addWidget(self.line_items_label)
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels(
            [
                _t("history.col_product"),
                _t("history.col_qty"),
                _t("history.col_unit_price"),
                _t("history.col_subtotal"),
            ]
        )
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.verticalHeader().setVisible(False)
        details_layout.addWidget(self.items_table)

        # Action Buttons
        action_layout = QHBoxLayout()
        self.reprint_btn = QPushButton(_t("history.reprint_receipt"))
        self.reprint_btn.clicked.connect(self.reprint_receipt)
        self.reprint_btn.setEnabled(False)
        action_layout.addWidget(self.reprint_btn)

        self.refund_btn = QPushButton(_t("history.process_refund"))
        self.refund_btn.clicked.connect(self.process_refund)
        self.refund_btn.setEnabled(False)
        self.refund_btn.setStyleSheet("background-color: #FF4136; color: white;")
        action_layout.addWidget(self.refund_btn)

        details_layout.addLayout(action_layout)
        details_layout.addStretch()

        splitter.addWidget(details_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def retranslate_ui(self) -> None:
        """Update all widget text from the translation system."""
        self.from_label.setText(_t("common.from"))
        self.to_label.setText(_t("common.to"))
        self.search_input.setPlaceholderText(_t("history.search_placeholder"))
        self.filter_btn.setText(_t("common.filter"))

        # Transaction table headers
        self.transaction_table.setHorizontalHeaderLabels(
            [
                _t("history.col_datetime"),
                _t("history.col_receipt"),
                _t("history.col_cashier"),
                _t("common.total"),
                _t("history.col_method"),
                _t("common.status"),
            ]
        )

        # Details panel
        self.details_title_label.setText(f"<b>{_t('history.transaction_details')}</b>")
        if not self.current_sale:
            self.details_label.setText(_t("history.select_transaction"))
        else:
            self.display_details(self.current_sale)
        self.line_items_label.setText(f"<b>{_t('history.line_items')}:</b>")

        # Items table headers
        self.items_table.setHorizontalHeaderLabels(
            [
                _t("history.col_product"),
                _t("history.col_qty"),
                _t("history.col_unit_price"),
                _t("history.col_subtotal"),
            ]
        )

        # Action buttons
        self.reprint_btn.setText(_t("history.reprint_receipt"))
        self.refund_btn.setText(_t("history.process_refund"))

    def load_today(self):
        """Load today's transactions"""
        self.apply_filter()

    def apply_filter(self):
        """Apply date range and search filters"""
        from_date = self.from_date.date().toPyDate()
        to_date = self.to_date.date().toPyDate()
        search_term = self.search_input.text().strip() or None

        sales = SaleQueryService.get_sales_history(
            from_date=datetime.combine(from_date, datetime.min.time()),
            to_date=datetime.combine(to_date, datetime.max.time()),
            search_term=search_term,
        )

        self.populate_table(sales)

    def populate_table(self, sales):
        """Populate transaction table with sales data"""
        self.transaction_table.setRowCount(0)

        for row, sale in enumerate(sales):
            self.transaction_table.insertRow(row)

            # Date/Time
            dt_item = RelativeTimeTableWidgetItem(sale.date)
            dt_item.setData(Qt.ItemDataRole.UserRole, sale.id)
            self.transaction_table.setItem(row, 0, dt_item)

            # Receipt#
            self.transaction_table.setItem(row, 1, QTableWidgetItem(sale.document_number))

            # Cashier
            cashier_name = sale.user.username if sale.user else _t("history.unknown")
            self.transaction_table.setItem(row, 2, QTableWidgetItem(cashier_name))

            # Total
            total_item = QTableWidgetItem(format_currency(sale.total_amount))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.transaction_table.setItem(row, 3, total_item)

            # Method
            self.transaction_table.setItem(row, 4, QTableWidgetItem(sale.payment_method))

            # Status
            status_item = QTableWidgetItem(sale.status)
            if sale.status == "VOID":
                status_item.setForeground(status_color(DANGER))
            elif sale.payment_method == "REFUND":
                status_item.setForeground(status_color(WARNING))
                status_item.setText(_t("history.status_refund"))
            self.transaction_table.setItem(row, 5, status_item)

    def on_selection_changed(self):
        """Handle selection change in transaction table"""
        selected_rows = self.transaction_table.selectedItems()
        if not selected_rows:
            self.current_sale = None
            self.reprint_btn.setEnabled(False)
            self.refund_btn.setEnabled(False)
            return

        # Get sale ID from first column
        sale_id = self.transaction_table.item(selected_rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

        # Load sale details
        sale = SaleQueryService.get_sale_details(sale_id)
        if sale:
            self.current_sale = sale
            self.display_details(sale)
            self.reprint_btn.setEnabled(True)
            # Enable refund only for completed non-refund sales
            self.refund_btn.setEnabled(sale.status == "COMPLETED" and sale.payment_method != "REFUND")

    def display_details(self, sale):
        """Display sale details in details panel"""
        cashier = sale.user.username if sale.user else _t("history.unknown")
        exact_date = sale.date.strftime("%Y-%m-%d %H:%M:%S")
        rel_date = format_relative_time(sale.date)
        details_text = f"""
        <b>{_t("history.detail_receipt")}:</b> {sale.document_number}<br>
        <b>{_t("common.date")}:</b> {rel_date} ({exact_date})<br>
        <b>{_t("history.col_cashier")}:</b> {cashier}<br>

        <b>{_t("common.total")}:</b> {format_currency(sale.total_amount)}<br>
        <b>{_t("history.detail_payment")}:</b> {sale.payment_method}<br>
        <b>{_t("common.status")}:</b> {sale.status}
        """

        if sale.refund_of_sale_id:
            details_text += f"<br><b>{_t('history.refund_of_sale')}:</b> #{sale.refund_of_sale_id}"

        self.details_label.setText(details_text)

        # Populate line items
        self.items_table.setRowCount(0)
        for row_idx, item in enumerate(sale.items):
            self.items_table.insertRow(row_idx)

            # Product name
            product_name = item.product.name_en if item.product else _t("history.unknown")
            self.items_table.setItem(row_idx, 0, QTableWidgetItem(product_name))

            # Quantity
            qty_item = QTableWidgetItem(f"{item.qty:.3f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row_idx, 1, qty_item)

            # Unit Price
            price_item = QTableWidgetItem(f"{item.unit_price:.2f}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row_idx, 2, price_item)

            # Subtotal
            subtotal_item = QTableWidgetItem(f"{item.subtotal:.2f}")
            subtotal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row_idx, 3, subtotal_item)

    def on_double_click(self):
        """Handle double-click to show full details"""
        if self.current_sale:
            self.reprint_receipt()

    def reprint_receipt(self):
        """Reprint the selected receipt"""
        if not self.current_sale:
            return

        try:
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
            except TypeError:
                pass  # not connected yet
            with contextlib.suppress(TypeError):
                worker.job_completed.disconnect(self._on_reprint_finished)
            worker.error_occurred.connect(self._on_reprint_error)
            worker.job_completed.connect(self._on_reprint_finished)

            PrinterService.print_receipt(self.current_sale, is_reprint=True)
        except Exception as e:
            logger.error("Reprint failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), _t("history.reprint_failed"))

    def _on_reprint_finished(self) -> None:
        """Called once the queued print job actually completes."""
        QMessageBox.information(
            self,
            _t("common.success"),
            _t("history.receipt_sent", receipt=self.current_sale.document_number),
        )

    def _on_reprint_error(self, message: str) -> None:
        """Called if the queued print job actually fails (e.g. no printer configured)."""
        logger.error("Reprint failed: %s", message)
        QMessageBox.critical(self, _t("common.error"), _t("history.reprint_failed"))

    def process_refund(self):
        """Process a refund for the selected sale"""
        if not self.current_sale:
            return

        # Confirmation -- what is handed back vs. taken off credit (#715)
        doc_number = self.current_sale.document_number
        breakdown = TransactionService.refund_breakdown(self.current_sale.id)
        if breakdown is None:
            QMessageBox.critical(self, _t("common.error"), _t("history.refund_failed"))
            return
        reply = QMessageBox.question(
            self,
            _t("history.confirm_refund"),
            refund_confirm_html(
                doc_number,
                breakdown,
                question=_t("history.refund_transaction_q"),
                receipt_label=_t("history.detail_receipt"),
                warning=_t("history.refund_warning"),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                current_user = AuthService.get_current_user()
                if not current_user:
                    QMessageBox.warning(self, _t("common.error"), _t("history.no_user_logged_in"))
                    return

                success = TransactionService.process_refund(self.current_sale.id, "Customer Return", current_user.id)

                if success:
                    QMessageBox.information(self, _t("common.success"), refund_done_text(doc_number, breakdown))
                    self.apply_filter()  # Refresh list
                else:
                    QMessageBox.critical(self, _t("common.error"), _t("history.refund_failed"))
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), _t("history.refund_error", error=e))
