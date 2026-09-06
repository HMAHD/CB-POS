import logging
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QLineEdit,
    QTextEdit,
    QSplitter,
    QWidget,
    QMessageBox,
    QFrame,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class SaleHistoryDialog(QDialog):
    """Dialog to browse recent sales, view details, reprint receipts, and process refunds."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SaleHistoryDialog")
        self.setWindowTitle(_t("sale_history.title"))
        self.setMinimumSize(950, 650)
        self.resize(950, 650)

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

        # --- Quick filter bar ---
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

        # --- Splitter: sales table (top) + details panel (bottom) ---
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # Top: sales table
        self.sales_table = QTableWidget()
        self.sales_table.setObjectName("SaleHistoryTable")
        self.sales_table.setColumnCount(5)
        self.sales_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sales_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sales_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sales_table.setAlternatingRowColors(True)
        self.sales_table.verticalHeader().setVisible(False)
        self.sales_table.horizontalHeader().setStretchLastSection(False)
        self.sales_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.sales_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.sales_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.currentItemChanged.connect(self._on_sale_selected)
        self.splitter.addWidget(self.sales_table)

        # Bottom: details panel
        self.details_widget = QWidget()
        self.details_widget.setObjectName("SaleHistoryDetails")
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(8, 8, 8, 8)
        details_layout.setSpacing(6)

        self.lbl_details_title = QLabel()
        self.lbl_details_title.setProperty("class", "bold")
        details_layout.addWidget(self.lbl_details_title)

        # Sale info grid
        self.info_frame = QFrame()
        self.info_frame.setObjectName("SaleInfoFrame")
        info_layout = QHBoxLayout(self.info_frame)
        info_layout.setContentsMargins(8, 4, 8, 4)

        # Left column
        left_col = QVBoxLayout()
        self.lbl_info_receipt = QLabel()
        self.lbl_info_receipt.setProperty("class", "transparent")
        left_col.addWidget(self.lbl_info_receipt)
        self.lbl_info_cashier = QLabel()
        self.lbl_info_cashier.setProperty("class", "transparent")
        left_col.addWidget(self.lbl_info_cashier)
        self.lbl_info_payment = QLabel()
        self.lbl_info_payment.setProperty("class", "transparent")
        left_col.addWidget(self.lbl_info_payment)
        info_layout.addLayout(left_col)

        # Right column
        right_col = QVBoxLayout()
        self.lbl_info_date = QLabel()
        self.lbl_info_date.setProperty("class", "transparent")
        right_col.addWidget(self.lbl_info_date)
        self.lbl_info_customer = QLabel()
        self.lbl_info_customer.setProperty("class", "transparent")
        right_col.addWidget(self.lbl_info_customer)
        self.lbl_info_status = QLabel()
        self.lbl_info_status.setProperty("class", "transparent")
        right_col.addWidget(self.lbl_info_status)
        info_layout.addLayout(right_col)

        details_layout.addWidget(self.info_frame)

        # Prompt label (shown when no sale selected)
        self.lbl_select_prompt = QLabel()
        self.lbl_select_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_select_prompt.setProperty("class", "transparent")
        details_layout.addWidget(self.lbl_select_prompt)

        # Line items table
        self.items_table = QTableWidget()
        self.items_table.setObjectName("SaleHistoryItems")
        self.items_table.setColumnCount(4)
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setAlternatingRowColors(True)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        details_layout.addWidget(self.items_table)

        self.splitter.addWidget(self.details_widget)
        self.splitter.setSizes([300, 350])
        layout.addWidget(self.splitter)

        # --- Action bar ---
        self.action_bar = QWidget()
        action_layout = QHBoxLayout(self.action_bar)
        action_layout.setContentsMargins(0, 4, 0, 0)
        action_layout.addStretch()

        self.btn_reprint = QPushButton()
        self.btn_reprint.setObjectName("SaleHistoryReprint")
        self.btn_reprint.setProperty("class", "accent")
        self.btn_reprint.setEnabled(False)
        self.btn_reprint.clicked.connect(self._reprint_receipt)
        action_layout.addWidget(self.btn_reprint)

        self.btn_refund = QPushButton()
        self.btn_refund.setObjectName("SaleHistoryRefund")
        self.btn_refund.setProperty("class", "danger")
        self.btn_refund.setEnabled(False)
        self.btn_refund.clicked.connect(self._start_refund)
        action_layout.addWidget(self.btn_refund)

        self.btn_close = QPushButton()
        self.btn_close.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_close)

        layout.addWidget(self.action_bar)

        # --- Refund inline panel (initially hidden) ---
        self.refund_panel = QFrame()
        self.refund_panel.setObjectName("RefundInlinePanel")
        self.refund_panel.setVisible(False)
        refund_layout = QVBoxLayout(self.refund_panel)
        refund_layout.setContentsMargins(10, 10, 10, 10)
        refund_layout.setSpacing(8)

        self.lbl_refund_header = QLabel()
        self.lbl_refund_header.setProperty("class", "bold")
        refund_layout.addWidget(self.lbl_refund_header)

        self.lbl_refund_reason = QLabel()
        refund_layout.addWidget(self.lbl_refund_reason)

        self.txt_refund_reason = QTextEdit()
        self.txt_refund_reason.setMaximumHeight(70)
        refund_layout.addWidget(self.txt_refund_reason)

        refund_btn_layout = QHBoxLayout()
        refund_btn_layout.addStretch()

        self.btn_cancel_refund = QPushButton()
        self.btn_cancel_refund.clicked.connect(self._cancel_refund)
        refund_btn_layout.addWidget(self.btn_cancel_refund)

        self.btn_confirm_refund = QPushButton()
        self.btn_confirm_refund.setProperty("class", "danger")
        self.btn_confirm_refund.clicked.connect(self._confirm_refund)
        refund_btn_layout.addWidget(self.btn_confirm_refund)

        refund_layout.addLayout(refund_btn_layout)
        layout.addWidget(self.refund_panel)

        # Set default filter
        self._filter_buttons["today"].setChecked(True)

        # Initial state: hide detail info, show prompt
        self._show_detail_state(False)

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

        self.lbl_details_title.setText(_t("sale_history.sale_details"))
        self.lbl_select_prompt.setText(_t("sale_history.select_sale_prompt"))

        self.items_table.setHorizontalHeaderLabels(
            [
                _t("sale_history.col_product"),
                _t("sale_history.col_qty"),
                _t("sale_history.col_unit_price"),
                _t("sale_history.col_subtotal"),
            ]
        )

        self.btn_reprint.setText(_t("sale_history.btn_reprint"))
        self.btn_refund.setText(_t("sale_history.btn_refund"))
        self.btn_close.setText(_t("sale_history.btn_close"))

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
        self.sales_table.setRowCount(0)

        if not self._sales:
            # Show empty state
            self.sales_table.setRowCount(1)
            item = QTableWidgetItem(_t("sale_history.no_sales_found"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.sales_table.setItem(0, 0, item)
            self.sales_table.setSpan(0, 0, 1, 5)
            return

        for idx, sale in enumerate(self._sales):
            row = self.sales_table.rowCount()
            self.sales_table.insertRow(row)

            # Receipt #
            receipt_item = QTableWidgetItem(sale.document_number or f"#{sale.id}")
            receipt_item.setData(Qt.ItemDataRole.UserRole, idx)
            self.sales_table.setItem(row, 0, receipt_item)

            # Date/Time
            date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
            self.sales_table.setItem(row, 1, QTableWidgetItem(date_str))

            # Customer
            customer_name = sale.customer.name if sale.customer else _t("sale_history.walk_in")
            self.sales_table.setItem(row, 2, QTableWidgetItem(customer_name))

            # Total (right-aligned)
            total_item = QTableWidgetItem(format_currency(sale.total_amount))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.sales_table.setItem(row, 3, total_item)

            # Status (colored)
            status = sale.status or "COMPLETED"
            status_item = QTableWidgetItem(self._get_status_display(status))

            if status == "COMPLETED":
                status_item.setForeground(QBrush(QColor("#39FF14")))
            elif status == "VOID":
                status_item.setForeground(QBrush(QColor("#FF4136")))
            elif sale.payment_method == "REFUND":
                status_item.setForeground(QBrush(QColor("#FFDC00")))

            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sales_table.setItem(row, 4, status_item)

    def _get_status_display(self, status: str) -> str:
        """Return translated status text."""
        status_map = {
            "COMPLETED": _t("sale_history.status_completed"),
            "VOID": _t("sale_history.status_void"),
            "REFUNDED": _t("sale_history.status_refunded"),
        }
        return status_map.get(status, status)

    # ── Sale selection ────────────────────────────────────────────

    def _on_sale_selected(self, current: QTableWidgetItem, previous: QTableWidgetItem) -> None:
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
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        customer_name = sale.customer.name if sale.customer else _t("sale_history.walk_in")
        cashier_name = sale.user.username if sale.user else "N/A"
        payment_method = sale.payment_method or "N/A"
        status = sale.status or "COMPLETED"

        self.lbl_info_receipt.setText(f"{_t('sale_history.detail_receipt')} {sale.document_number}")
        self.lbl_info_date.setText(f"{_t('sale_history.detail_date')} {date_str}")
        self.lbl_info_cashier.setText(f"{_t('sale_history.detail_cashier')} {cashier_name}")
        self.lbl_info_customer.setText(f"{_t('sale_history.detail_customer')} {customer_name}")
        self.lbl_info_payment.setText(f"{_t('sale_history.detail_payment')} {payment_method}")
        self.lbl_info_status.setText(f"{_t('sale_history.detail_status')} {status}")

        # Populate line items
        self.items_table.setRowCount(0)
        for item in sale.items:
            r = self.items_table.rowCount()
            self.items_table.insertRow(r)

            product_name = item.product.name_en if item.product else "?"
            self.items_table.setItem(r, 0, QTableWidgetItem(product_name))
            self.items_table.setItem(r, 1, QTableWidgetItem(str(item.qty)))

            price_item = QTableWidgetItem(format_currency(item.unit_price))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(r, 2, price_item)

            sub_item = QTableWidgetItem(format_currency(item.subtotal))
            sub_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(r, 3, sub_item)

        # Enable/disable action buttons
        self.btn_reprint.setEnabled(True)
        can_refund = status not in ("VOID", "REFUNDED") and sale.payment_method != "REFUND"
        self.btn_refund.setEnabled(can_refund)

    def _show_detail_state(self, has_selection: bool) -> None:
        """Toggle between prompt label and detail info."""
        self.lbl_select_prompt.setVisible(not has_selection)
        self.info_frame.setVisible(has_selection)
        self.items_table.setVisible(has_selection)

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
            worker.add_job("print_receipt", commands)
            QMessageBox.information(
                self,
                _t("sale_history.title"),
                _t("sale_history.reprint_success"),
            )
        except Exception as e:
            logger.error("Reprint failed: %s", e)
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("sale_history.reprint_failed", error=str(e)),
            )

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

        # Confirmation dialog
        sale = self._selected_sale
        reply = QMessageBox.question(
            self,
            _t("common.confirm"),
            _t(
                "sale_history.refund_header",
                receipt=sale.document_number,
                amount=format_currency(sale.total_amount),
            )
            + f"\n\n{reason}",
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
                    _t(
                        "sale_history.refund_success",
                        amount=format_currency(sale.total_amount),
                    ),
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
            QMessageBox.warning(self, _t("common.warning"), str(e))
        except Exception as e:
            logger.error("Refund failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), str(e))
        finally:
            self.btn_confirm_refund.setEnabled(True)
