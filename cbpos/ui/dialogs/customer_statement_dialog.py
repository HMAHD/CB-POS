"""
Dialog for viewing and printing customer account statements.
"""

import contextlib
import logging

from PyQt6.QtCore import QDate, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.statement_service import StatementService
from cbpos.core.utils.date_ranges import range_for
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import INFO, NEUTRAL, SUCCESS, WARNING
from cbpos.ui.widgets.status_pill_delegate import StatusPillDelegate, set_status_pill
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    RelativeTimeTableWidgetItem,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

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


class CustomerStatementDialog(QDialog):
    """Dialog to view and print a customer account statement."""

    def __init__(self, customer, parent=None):
        """Initialize the dialog and load the statement for the given customer."""
        super().__init__(parent)
        self.customer = customer
        self.statement_data = None

        self.setWindowTitle(_t("customer_statement.title", name=customer.name))
        self.setMinimumSize(840, 620)
        self.setObjectName("CustomerStatementDialog")
        self._init_ui()
        self._load_statement()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Customer Hero Card
        header_card = QFrame()
        header_card.setObjectName("StatementHeaderCard")
        card_layout = QHBoxLayout(header_card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(12)

        # Avatar Icon
        lbl_avatar = QLabel()
        lbl_avatar.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(36, 36))
        card_layout.addWidget(lbl_avatar)

        # Name and metadata
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(4)

        top_line = QHBoxLayout()
        top_line.setSpacing(10)
        self.lbl_customer = QLabel(f"{self.customer.name}")
        self.lbl_customer.setObjectName("StatementCustName")
        top_line.addWidget(self.lbl_customer)

        lbl_id = QLabel(f"#CUST-{self.customer.id:04d}")
        lbl_id.setObjectName("StatementCustId")
        top_line.addWidget(lbl_id)
        top_line.addStretch()
        meta_layout.addLayout(top_line)

        # Phone line
        phone_line = QHBoxLayout()
        phone_line.setSpacing(6)
        lbl_phone_icon = QLabel()
        lbl_phone_icon.setPixmap(Icons.get("fa5s.phone-alt", "#94A3B8").pixmap(12, 12))
        phone_line.addWidget(lbl_phone_icon)

        phone_text = self.customer.phone or "---"
        self.lbl_phone = QLabel(_t("customer_statement.phone", phone=phone_text))
        self.lbl_phone.setObjectName("StatementCustPhone")
        phone_line.addWidget(self.lbl_phone)
        phone_line.addStretch()
        meta_layout.addLayout(phone_line)

        card_layout.addLayout(meta_layout)
        card_layout.addStretch()

        layout.addWidget(header_card)

        # 2. Date filter row with tuned spacing and presets
        self.filter_layout = filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 6, 0, 6)
        filter_layout.setSpacing(10)

        lbl_from = QLabel(_t("common.from"))
        lbl_from.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_from)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.date_from)

        lbl_to = QLabel(_t("common.to"))
        lbl_to.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_to)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.date_to)

        # Preset buttons
        self.btn_preset_month = QPushButton(_t("customer_statement.preset_month"))
        self.btn_preset_month.setProperty("class", "secondary")
        self.btn_preset_month.clicked.connect(self._set_preset_this_month)
        filter_layout.addWidget(self.btn_preset_month)

        self.btn_preset_30d = QPushButton(_t("customer_statement.preset_30d"))
        self.btn_preset_30d.setProperty("class", "secondary")
        self.btn_preset_30d.clicked.connect(self._set_preset_last_30d)
        filter_layout.addWidget(self.btn_preset_30d)

        self.btn_preset_all = QPushButton(_t("customer_statement.preset_all"))
        self.btn_preset_all.setProperty("class", "secondary")
        self.btn_preset_all.clicked.connect(self._set_preset_all_time)
        filter_layout.addWidget(self.btn_preset_all)

        btn_refresh = QPushButton(_t("common.refresh"))
        btn_refresh.setProperty("class", "accent")
        _set_button_icon(btn_refresh, "fa5s.sync-alt", "#FFFFFF", pad_right=8, size=12)
        btn_refresh.clicked.connect(self._load_statement)
        filter_layout.addWidget(btn_refresh)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # 3. 5-Way Reconciled Summary Grid
        self.summary_layout = summary_layout = QGridLayout()
        summary_layout.setHorizontalSpacing(16)
        summary_layout.setVerticalSpacing(10)

        # Labels for test compatibility and clean styling
        self.lbl_opening = QLabel(_t("customer_statement.opening", value="---"))
        self.lbl_opening.setProperty("class", "statement-stat")
        self.lbl_opening.setObjectName("StatOpening")

        self.lbl_total_debit = QLabel(_t("customer_statement.sales", value="---"))
        self.lbl_total_debit.setProperty("class", "statement-stat debit")
        self.lbl_total_debit.setObjectName("StatSales")

        self.lbl_adjustments = QLabel(_t("customer_statement.adjustments", value="---"))
        self.lbl_adjustments.setProperty("class", "statement-stat")
        self.lbl_adjustments.setObjectName("StatAdjustments")

        self.lbl_total_credit = QLabel(_t("customer_statement.payments", value="---"))
        self.lbl_total_credit.setProperty("class", "statement-stat credit")
        self.lbl_total_credit.setObjectName("StatPayments")

        self.lbl_closing = QLabel(_t("customer_statement.closing", value="---"))
        self.lbl_closing.setProperty("class", "statement-stat bold")
        self.lbl_closing.setObjectName("StatClosing")

        # Row 0: Opening (0, 0), Sales (0, 1), Adjustments (0, 2)
        summary_layout.addWidget(self.lbl_opening, 0, 0)
        summary_layout.addWidget(self.lbl_total_debit, 0, 1)
        summary_layout.addWidget(self.lbl_adjustments, 0, 2)

        # Row 1: Payments (1, 0), Empty/Spacer (1, 1), Closing (1, 2)
        summary_layout.addWidget(self.lbl_total_credit, 1, 0)
        summary_layout.addWidget(self.lbl_closing, 1, 2)

        summary_layout.setColumnStretch(0, 1)
        summary_layout.setColumnStretch(1, 1)
        summary_layout.setColumnStretch(2, 1)
        layout.addLayout(summary_layout)

        # 4. Entries table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                _t("customer_statement.col_date"),
                _t("customer_statement.col_type"),
                _t("customer_statement.col_description"),
                _t("customer_statement.col_debit"),
                _t("customer_statement.col_credit"),
                _t("customer_statement.col_balance"),
            ]
        )
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.Stretch,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
                5: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        self.table.setItemDelegateForColumn(1, StatusPillDelegate(self.table))
        attach_table_empty_state(self.table, Icons.DOCUMENTS, "customer_statement.no_transactions")
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        align_numeric_headers(self.table, [3, 4, 5])
        layout.addWidget(self.table)

        # 5. Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        btn_print = QPushButton(_t("customer_statement.print_statement"))
        btn_print.setProperty("class", "accent")
        _set_button_icon(btn_print, "fa5s.print", "#FFFFFF", pad_right=8, size=13)
        btn_print.clicked.connect(self._print_thermal)
        btn_layout.addWidget(btn_print)

        btn_close = QPushButton(_t("common.close"))
        btn_close.setObjectName("BtnCancel")
        btn_close.setProperty("class", "secondary")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _set_preset_this_month(self) -> None:
        today = QDate.currentDate()
        self.date_from.setDate(QDate(today.year(), today.month(), 1))
        self.date_to.setDate(today)
        self._load_statement()

    def _set_preset_last_30d(self) -> None:
        today = QDate.currentDate()
        self.date_from.setDate(today.addDays(-30))
        self.date_to.setDate(today)
        self._load_statement()

    def _set_preset_all_time(self) -> None:
        today = QDate.currentDate()
        self.date_from.setDate(today.addYears(-5))
        self.date_to.setDate(today)
        self._load_statement()

    def _get_date_range(self) -> tuple:
        d_from = self.date_from.date().toPyDate()
        d_to = self.date_to.date().toPyDate()
        return range_for(d_from, d_to)

    def _load_statement(self) -> None:
        """Load statement data and populate the table."""
        from_dt, to_dt = self._get_date_range()

        try:
            self.statement_data = StatementService.generate_statement(
                customer_id=self.customer.id,
                date_from=from_dt,
                date_to=to_dt,
            )
        except Exception as e:
            logger.error("Failed to load statement: %s", e)
            QMessageBox.critical(
                self, _t("common.error"), _t("customer_statement.load_failed", error=translate_error(str(e)))
            )
            return

        data = self.statement_data

        # Update 5-way summaries
        self.lbl_opening.setText(_t("customer_statement.opening", value=format_currency(data["opening_balance"])))
        self.lbl_total_debit.setText(
            _t("customer_statement.sales", value=format_currency(data.get("total_sales", data["total_debit"])))
        )
        self.lbl_total_credit.setText(
            _t("customer_statement.payments", value=format_currency(data.get("total_payments", data["total_credit"])))
        )
        self.lbl_adjustments.setText(
            _t("customer_statement.adjustments", value=format_currency(data.get("net_adjustments", 0)))
        )
        self.lbl_closing.setText(_t("customer_statement.closing", value=format_currency(data["closing_balance"])))

        # Populate table
        with batch_table_update(self.table):
            self.table.setRowCount(0)
            entries = data["entries"]
            if not entries:
                return

            TableItem = QTableWidgetItem
            RelTimeItem = RelativeTimeTableWidgetItem
            fmt_curr = format_currency
            num_align = NUMERIC_ALIGNMENT
            set_pill = set_status_pill
            set_item = self.table.setItem
            insert_row = self.table.insertRow

            for entry in entries:
                row = self.table.rowCount()
                insert_row(row)

                set_item(row, 0, RelTimeItem(entry["date"], fmt="%Y-%m-%d"))
                type_str = entry["type"]
                meaning = (
                    SUCCESS
                    if type_str in ("PAYMENT", "CREDIT")
                    else (
                        WARNING
                        if type_str in ("SALE", "INVOICE", "DEBIT")
                        else (INFO if type_str in ("ADJUSTMENT", "REFUND") else NEUTRAL)
                    )
                )
                type_item = TableItem(type_str)
                set_pill(type_item, type_str, meaning)
                set_item(row, 1, type_item)
                set_item(row, 2, TableItem(entry["description"]))

                debit_str = fmt_curr(entry["debit"]) if entry["debit"] > 0 else ""
                credit_str = fmt_curr(entry["credit"]) if entry["credit"] > 0 else ""

                item_debit = TableItem(debit_str)
                item_debit.setTextAlignment(num_align)
                set_item(row, 3, item_debit)

                item_credit = TableItem(credit_str)
                item_credit.setTextAlignment(num_align)
                set_item(row, 4, item_credit)

                item_balance = TableItem(fmt_curr(entry["balance"]))
                item_balance.setTextAlignment(num_align)
                set_item(row, 5, item_balance)

    def _print_thermal(self) -> None:
        """Print statement on thermal printer."""
        from_dt, to_dt = self._get_date_range()

        entries = CustomerCreditService.get_ledger(
            self.customer.id,
            date_from=from_dt,
            date_to=to_dt,
        )

        commands = ReceiptBuilder.build_customer_statement(
            customer=self.customer,
            entries=entries,
            period_from=from_dt,
            period_to=to_dt,
        )

        worker = PrintWorker.instance()
        try:
            worker.error_occurred.disconnect(self._on_print_error)
        except TypeError as e:
            logger.debug("Signal not connected yet: %s", e)
        with contextlib.suppress(TypeError):
            worker.job_completed.disconnect(self._on_print_finished)
        worker.error_occurred.connect(self._on_print_error)
        worker.job_completed.connect(self._on_print_finished)
        worker.add_job("print_commands", commands)

    def _on_print_finished(self) -> None:
        """Called once the queued print job actually completes."""
        QMessageBox.information(self, _t("common.print"), _t("customer_statement.print_sent"))

    def _on_print_error(self, message: str) -> None:
        """Called if the queued print job actually fails (e.g. no printer configured)."""
        logger.error("Statement print failed: %s", message)
        QMessageBox.critical(self, _t("common.error"), _t("customer_statement.print_failed"))
