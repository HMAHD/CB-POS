import contextlib
import logging
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
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
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency, format_datetime, format_relative_time
from cbpos.i18n import _t
from cbpos.ui.refund_messages import refund_confirm_text, refund_done_text
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, SUCCESS, WARNING, status_color
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
        self.splitter.addWidget(self.sales_table)

        # Right: details panel (receipt inspector)
        self.details_widget = QFrame()
        self.details_widget.setObjectName("SaleHistoryDetails")
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(6)

        self.lbl_details_title = QLabel()
        self.lbl_details_title.setProperty("class", "bold")
        details_layout.addWidget(self.lbl_details_title)

        # Prompt label (shown when no sale selected)
        self.lbl_select_prompt = QLabel()
        self.lbl_select_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_select_prompt.setProperty("class", "transparent")
        details_layout.addWidget(self.lbl_select_prompt, 1)

        # Scroll area for receipt preview
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setObjectName("SaleReceiptScroll")
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self.receipt_preview = ReceiptPreviewWidget()
        self.preview_scroll.setWidget(self.receipt_preview)
        details_layout.addWidget(self.preview_scroll, 1)

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
        self.lbl_info_cashier = QLabel(self.info_frame)
        self.lbl_info_payment = QLabel(self.info_frame)
        self.lbl_info_date = QLabel(self.info_frame)
        self.lbl_info_customer = QLabel(self.info_frame)
        self.lbl_info_status = QLabel(self.info_frame)
        self.items_table = QTableWidget(self.info_frame)

        self.btn_reprint = QPushButton()
        self.btn_reprint.setVisible(False)
        self.btn_reprint.clicked.connect(self._reprint_receipt)

        self.btn_refund = QPushButton()
        self.btn_refund.setVisible(False)
        self.btn_refund.clicked.connect(self._start_refund)

        self.refund_panel = QFrame()
        self.refund_panel.setVisible(False)
        self.lbl_refund_header = QLabel(self.refund_panel)
        self.lbl_refund_reason = QLabel(self.refund_panel)
        self.txt_refund_reason = QTextEdit(self.refund_panel)
        self.btn_confirm_refund = QPushButton(self.refund_panel)
        self.btn_confirm_refund.clicked.connect(self._confirm_refund)
        self.btn_cancel_refund = QPushButton(self.refund_panel)
        self.btn_cancel_refund.clicked.connect(self._cancel_refund)

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

        # Retained widget labels for tests
        self.btn_reprint.setText(_t("sale_history.btn_reprint"))
        self.btn_refund.setText(_t("sale_history.btn_refund"))
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

        try:
            self._sales = SaleQueryService.get_sales_history(
                from_date=from_date,
                to_date=to_date,
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

                # Status (colored)
                status = sale.status or "COMPLETED"
                status_text = self._get_status_display(status)
                status_item = TableItem(status_text)

                if status == "COMPLETED":
                    status_item.setForeground(succ_color)
                    set_pill(status_item, status_text, "success")
                elif status == "VOID":
                    status_item.setForeground(dang_color)
                    set_pill(status_item, status_text, "danger")
                elif sale.payment_method == "REFUND":
                    status_item.setForeground(warn_color)
                    set_pill(status_item, status_text, "warning")
                else:
                    set_pill(status_item, status_text, "neutral")

                status_item.setTextAlignment(align_center)
                set_item(row, 4, status_item)

    def _get_status_display(self, status: str) -> str:
        """Return translated status text."""
        status_map = {
            "COMPLETED": _t("sale_history.status_completed"),
            "VOID": _t("sale_history.status_void"),
            "REFUNDED": _t("sale_history.status_refunded"),
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

        # Populate info labels
        if sale.date:
            date_str = format_datetime(sale.date)
            rel_date = format_relative_time(sale.date)
            date_display = f"{rel_date} ({date_str})"
            self.lbl_info_date.setToolTip(date_str)
        else:
            date_display = "N/A"
            self.lbl_info_date.setToolTip("")
        customer_name = sale.customer.name if sale.customer else _t("sale_history.walk_in")
        cashier_name = sale.user.username if sale.user else "N/A"
        payment_method = sale.payment_method or "N/A"
        status = sale.status or "COMPLETED"

        self.lbl_info_receipt.setText(f"{_t('sale_history.detail_receipt')} {sale.document_number}")
        self.lbl_info_date.setText(f"{_t('sale_history.detail_date')} {date_display}")

        self.lbl_info_cashier.setText(f"{_t('sale_history.detail_cashier')} {cashier_name}")
        self.lbl_info_customer.setText(f"{_t('sale_history.detail_customer')} {customer_name}")
        self.lbl_info_payment.setText(f"{_t('sale_history.detail_payment')} {payment_method}")
        self.lbl_info_status.setText(f"{_t('sale_history.detail_status')} {status}")

        # Populate line items
        with batch_table_update(self.items_table):
            self.items_table.setRowCount(0)
            TableItem = QTableWidgetItem
            fmt_curr = format_currency
            num_align = NUMERIC_ALIGNMENT
            set_item = self.items_table.setItem
            insert_row = self.items_table.insertRow

            for item in sale.items:
                r = self.items_table.rowCount()
                insert_row(r)

                product_name = item.product.name_en if item.product else "?"
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

        # Render authentic receipt using system print settings
        try:
            paper_width = ConfigService.get("paper_width") or "80mm"
            self.receipt_preview.set_paper_width(paper_width)
            commands = ReceiptBuilder.build_receipt(sale)
            self.receipt_preview.set_commands(commands)
        except Exception as e:
            logger.error("Failed to build receipt preview for sale %s: %s", sale.id, e)
            self.receipt_preview.set_commands([])

        # Retained button states for tests
        self.btn_reprint.setEnabled(True)
        can_refund = status not in ("VOID", "REFUNDED") and sale.payment_method != "REFUND"
        self.btn_refund.setEnabled(can_refund)

    def _show_detail_state(self, has_selection: bool) -> None:
        """Toggle between prompt label and receipt preview."""
        self.lbl_select_prompt.setVisible(not has_selection)
        self.preview_scroll.setVisible(has_selection)
        if not has_selection:
            self.receipt_preview.set_commands([])

    # ── Reprint ───────────────────────────────────────────────────

    def _reprint_receipt(self) -> None:
        """Reprint receipt for the selected sale."""
        if not self._selected_sale:
            return

        try:
            from cbpos.core.services.receipt_builder import ReceiptBuilder
            from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

            commands = ReceiptBuilder.build_receipt(self._selected_sale, is_reprint=True)
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
            worker.add_job("print_receipt", commands)
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
        """Show inline refund panel, hide action bar."""
        if not self._selected_sale:
            return

        sale = self._selected_sale
        status = sale.status or "COMPLETED"
        if status in ("VOID", "REFUNDED") or sale.payment_method == "REFUND":
            QMessageBox.warning(
                self,
                _t("common.warning"),
                _t("sale_history.refund_not_eligible", status=status),
            )
            return

        self.lbl_refund_header.setText(
            _t(
                "sale_history.refund_header",
                receipt=sale.document_number,
                amount=format_currency(sale.total_amount),
            )
        )
        self.txt_refund_reason.clear()
        self.action_bar.setVisible(False)
        self.refund_panel.setVisible(True)

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
