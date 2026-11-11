import logging
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDateEdit,
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
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.utils.formatters import format_currency, format_datetime
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget
from cbpos.ui.widgets.status_pill_delegate import StatusPillDelegate, set_status_pill
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class ReceiptReprintDialog(QDialog):
    """Dialog to search past sales and reprint receipts with live thermal preview."""

    def __init__(self, parent=None):
        """Build the dialog with quick filter chips, results table, and live receipt preview."""
        super().__init__(parent)
        self.setWindowTitle(_t("receipt_reprint.title"))
        self.setMinimumSize(1050, 600)
        self.setObjectName("ReceiptReprintDialog")
        self.results = []
        self._selected_sale = None
        self._active_filter = "today"
        self._reprint_job_id: str | None = None
        PrintWorker.instance().job_result.connect(self._on_reprint_job_result)
        self._init_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)
        self.perform_search()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Horizontal splitter between table and live preview
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left Pane: Search & Results Table ───────────────────────
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Filter buttons and Search bar
        top_filter_layout = QHBoxLayout()
        top_filter_layout.setSpacing(8)

        # Quick date filters
        self._filter_buttons = {}
        for key, i18n_key in (
            ("today", "receipt_reprint.filter_today"),
            ("yesterday", "receipt_reprint.filter_yesterday"),
            ("this_week", "receipt_reprint.filter_this_week"),
            ("this_month", "receipt_reprint.filter_this_month"),
        ):
            btn = QPushButton(_t(i18n_key))
            btn.setObjectName("FilterChip")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key: self._on_filter_clicked(k))
            top_filter_layout.addWidget(btn)
            self._filter_buttons[key] = btn

        self._filter_buttons["today"].setChecked(True)
        top_filter_layout.addStretch()

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SaleSearchInput")
        self.search_input.setPlaceholderText(_t("receipt_reprint.search_placeholder"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self.perform_search)
        top_filter_layout.addWidget(self.search_input, 1)

        # Search debounce timer
        self._search_timer = QTimer(self)
        self._search_timer.setInterval(300)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self.perform_search)

        left_layout.addLayout(top_filter_layout)

        # Retained compatibility widgets for external tests
        self.date_from = QDateEdit()
        self.date_from.setVisible(False)
        self.date_to = QDateEdit()
        self.date_to.setVisible(False)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(
            [
                _t("common.id"),
                _t("receipt_reprint.col_receipt"),
                _t("common.date"),
                _t("receipt_reprint.col_customer"),
                _t("common.total"),
                _t("common.status"),
            ]
        )
        self.results_table.setColumnHidden(0, True)
        configure_table_columns(
            self.results_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,
                1: QHeaderView.ResizeMode.Interactive,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.Stretch,
                4: QHeaderView.ResizeMode.ResizeToContents,
                5: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        self.results_table.setColumnWidth(1, 140)
        align_numeric_headers(self.results_table, (4,))
        self.results_table.setItemDelegateForColumn(5, StatusPillDelegate(self.results_table))
        attach_table_empty_state(self.results_table, Icons.PRINT, "common.no_items")
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.doubleClicked.connect(self.reprint_selected)
        self.results_table.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.results_table)

        self.splitter.addWidget(left_pane)

        # ── Right Pane: Authentic Thermal Receipt Preview ────────────
        self.preview_container = QFrame()
        self.preview_container.setObjectName("ReceiptReprintPreviewContainer")
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(6)

        self.lbl_preview_title = QLabel(_t("receipt_reprint.preview_title"))
        self.lbl_preview_title.setProperty("class", "bold")
        preview_layout.addWidget(self.lbl_preview_title)

        self.lbl_preview_prompt = QLabel(_t("receipt_reprint.select_to_preview"))
        self.lbl_preview_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_prompt.setProperty("class", "transparent")
        preview_layout.addWidget(self.lbl_preview_prompt, 1)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setObjectName("SaleReceiptScroll")
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self.receipt_preview = ReceiptPreviewWidget()
        self.preview_scroll.setWidget(self.receipt_preview)
        preview_layout.addWidget(self.preview_scroll, 1)

        self.splitter.addWidget(self.preview_container)
        self.splitter.setSizes([600, 400])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        layout.addWidget(self.splitter, 1)

        # ── Action Bar ──────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_reprint = QPushButton(_t("receipt_reprint.btn_reprint"))
        self.btn_reprint.setProperty("class", "primary")
        self.btn_reprint.setEnabled(False)
        self.btn_reprint.clicked.connect(self.reprint_selected)
        btn_layout.addWidget(self.btn_reprint)

        self.btn_close = QPushButton(_t("common.close"))
        self.btn_close.setObjectName("BtnCancel")
        self.btn_close.setProperty("class", "secondary")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # Initial state
        self.lbl_preview_prompt.setVisible(True)
        self.preview_scroll.setVisible(False)

    def _on_selection_changed(
        self,
        current: QTableWidgetItem | None = None,
        previous: QTableWidgetItem | None = None,
    ) -> None:
        """Update thermal receipt preview when a transaction row is selected."""
        if not current:
            self._selected_sale = None
            self.lbl_preview_prompt.setVisible(True)
            self.preview_scroll.setVisible(False)
            self.btn_reprint.setEnabled(False)
            return

        row = current.row()
        if row < 0 or row >= len(self.results):
            return

        sale = self.results[row]
        self._selected_sale = sale
        if getattr(sale, "status", "") == "VOID":
            self.lbl_preview_prompt.setVisible(True)
            self.preview_scroll.setVisible(False)
            self.btn_reprint.setEnabled(False)
            self.btn_reprint.setToolTip(_t("reprint.void_blocked"))
            return

        self.btn_reprint.setToolTip("")
        try:
            paper_width = ConfigService.get("paper_width") or "80mm"
            self.receipt_preview.set_paper_width(paper_width)
            doc_number = getattr(sale, "document_number", "") or str(getattr(sale, "id", ""))
            is_refund = bool(
                getattr(sale, "refund_of_sale_id", None) is not None
                or getattr(sale, "payment_method", "") == "REFUND"
                or doc_number.startswith("CN-")
            )
            if is_refund:
                commands = ReceiptBuilder.build_refund_receipt(
                    sale=sale,
                    refund_amount=abs(sale.total_amount),
                    authorized_by=sale.user.username if getattr(sale, "user", None) else "",
                    is_reprint=True,
                )
            else:
                commands = ReceiptBuilder.build_receipt(sale, is_reprint=True)
            self.receipt_preview.set_commands(commands)
            self.lbl_preview_prompt.setVisible(False)
            self.preview_scroll.setVisible(True)
            self.btn_reprint.setEnabled(True)
        except Exception as e:
            logger.error("Failed to build reprint preview for sale %s: %s", getattr(sale, "id", None), e)
            self.lbl_preview_prompt.setVisible(True)
            self.preview_scroll.setVisible(False)
            self.btn_reprint.setEnabled(False)

    def _on_filter_clicked(self, key: str) -> None:
        """Handle quick filter button click."""
        self._active_filter = key
        for k, btn in self._filter_buttons.items():
            btn.setChecked(k == key)
        self.perform_search()

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
            return yesterday, today_start
        elif self._active_filter == "this_week":
            week_start = today_start - timedelta(days=today_start.weekday())
            return week_start, now
        elif self._active_filter == "this_month":
            month_start = today_start.replace(day=1)
            return month_start, now
        return today_start, now

    def perform_search(self) -> None:
        """Search for past sales by receipt number, customer, phone, or active date filter."""
        search_term = self.search_input.text().strip() or None
        from_dt, to_dt = self._get_date_range()

        query_from = None if search_term else from_dt
        query_to = None if search_term else to_dt

        try:
            self.results = SaleQueryService.get_sales_history(
                from_date=query_from,
                to_date=query_to,
                search_term=search_term,
                limit=100,
            )
            self._populate_table()
        except Exception as e:
            logger.error(f"Receipt search failed: {e}")
            QMessageBox.critical(self, _t("common.error"), _t("receipt_reprint.search_failed", error=e))

    def _populate_table(self) -> None:
        """Fill results table with sales data."""
        with batch_table_update(self.results_table):
            self.results_table.setRowCount(0)
            TableItem = QTableWidgetItem
            fmt_curr = format_currency
            fmt_dt = format_datetime
            num_align = NUMERIC_ALIGNMENT
            set_item = self.results_table.setItem
            insert_row = self.results_table.insertRow
            walk_in_text = _t("receipt_reprint.walk_in")

            for sale in self.results:
                row = self.results_table.rowCount()
                insert_row(row)

                status = getattr(sale, "status", None) or "COMPLETED"
                is_void = status == "VOID"
                doc_number = sale.document_number or f"#{sale.id}"
                is_refund_doc = (
                    getattr(sale, "payment_method", "") == "REFUND"
                    or bool(getattr(sale, "refund_of_sale_id", None))
                    or doc_number.startswith("CN-")
                )

                set_item(row, 0, TableItem(str(sale.id)))
                set_item(row, 1, TableItem(doc_number))

                date_str = fmt_dt(sale.date) if sale.date else "N/A"
                set_item(row, 2, TableItem(date_str))

                customer_name = sale.customer.name if sale.customer else walk_in_text
                set_item(row, 3, TableItem(customer_name))

                total_item = TableItem(fmt_curr(sale.total_amount))
                total_item.setTextAlignment(num_align)
                set_item(row, 4, total_item)

                status_item = TableItem()
                if is_void:
                    set_status_pill(status_item, _t("sale_history.status_void"), "danger")
                elif is_refund_doc:
                    set_status_pill(status_item, _t("sale_history.status_refunded"), "warning")
                else:
                    set_status_pill(status_item, _t("sale_history.status_completed"), "success")
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                set_item(row, 5, status_item)

                if is_void:
                    gray = Qt.GlobalColor.gray
                    for col in range(5):
                        it = self.results_table.item(row, col)
                        if it:
                            it.setForeground(gray)

    def reprint_selected(self) -> None:
        """Reprint receipt for the selected sale."""
        row = self.results_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, _t("receipt_reprint.no_selection"), _t("receipt_reprint.select_sale"))
            return

        sale = self.results[row]
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
            worker = PrintWorker.instance()
            self._reprint_job_id = worker.add_job("print_receipt", job.commands)
        except ValueError as e:
            if str(e) == "reprint_void":
                QMessageBox.warning(self, _t("common.warning"), _t("reprint.void_blocked"))
            else:
                QMessageBox.critical(self, _t("common.error"), _t("receipt_reprint.reprint_failed"))
        except Exception as e:
            logger.error(f"Reprint failed: {e}")
            QMessageBox.critical(self, _t("common.error"), _t("receipt_reprint.reprint_failed"))

    def _on_reprint_job_result(self, job_id: str, ok: bool, message: str) -> None:
        """Called when a print job completes. Ignores jobs other than this dialog's reprint (#842)."""
        if not self._reprint_job_id or job_id != self._reprint_job_id:
            return
        self._reprint_job_id = None
        if ok:
            QMessageBox.information(self, _t("receipt_reprint.title"), _t("receipt_reprint.reprint_success"))
        else:
            logger.error("Reprint failed: %s", message)
            QMessageBox.critical(self, _t("common.error"), _t("receipt_reprint.reprint_failed"))
