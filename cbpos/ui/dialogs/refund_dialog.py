import logging

from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.formatters import format_currency
from cbpos.core.utils.permission_helper import check_permission_with_override
from cbpos.i18n import _t
from cbpos.ui.refund_messages import refund_confirm_text, refund_done_text
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    configure_table_columns,
)

logger = logging.getLogger(__name__)


class RefundDialog(QDialog):
    """Dialog to search an original sale and process a full refund."""

    def __init__(self, parent=None):
        """Build the dialog with an empty receipt search field."""
        super().__init__(parent)
        self.setWindowTitle(_t("refund.title"))
        self.setMinimumSize(650, 500)
        self.setObjectName("RefundDialog")
        self.found_sale = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Search section
        search_layout = QHBoxLayout()
        self.lbl_receipt = QLabel("")
        self.lbl_receipt.setProperty("class", "bold")
        search_layout.addWidget(self.lbl_receipt)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("")
        self.search_input.returnPressed.connect(self.lookup_sale)
        search_layout.addWidget(self.search_input, 1)

        self.btn_lookup = QPushButton("")
        self.btn_lookup.setProperty("class", "primary")
        self.btn_lookup.clicked.connect(self.lookup_sale)
        search_layout.addWidget(self.btn_lookup)
        layout.addLayout(search_layout)

        # Sale details group
        self.details_group = QGroupBox("")
        details_layout = QVBoxLayout(self.details_group)

        self.lbl_sale_info = QLabel("")
        self.lbl_sale_info.setProperty("class", "transparent")
        details_layout.addWidget(self.lbl_sale_info)

        # Items table
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels(["", "", "", ""])
        configure_table_columns(
            self.items_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        attach_table_empty_state(self.items_table, Icons.SALES, "common.no_items")
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.setAlternatingRowColors(True)
        details_layout.addWidget(self.items_table)

        layout.addWidget(self.details_group)

        # Reason
        self.lbl_reason = QLabel("")
        self.lbl_reason.setProperty("class", "bold")
        layout.addWidget(self.lbl_reason)

        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText("")
        self.txt_reason.setMaximumHeight(80)
        layout.addWidget(self.txt_reason)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_refund = QPushButton("")
        self.btn_refund.setProperty("class", "danger")
        self.btn_refund.setEnabled(False)
        self.btn_refund.clicked.connect(self.process_refund)
        btn_layout.addWidget(self.btn_refund)

        self.btn_cancel = QPushButton("")
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("refund.title"))
        self.lbl_receipt.setText(_t("refund.receipt_label"))
        self.search_input.setPlaceholderText(_t("refund.receipt_placeholder"))
        self.btn_lookup.setText(_t("refund.btn_lookup"))
        self.details_group.setTitle(_t("refund.group_title"))
        self.lbl_sale_info.setText(_t("refund.no_sale_loaded"))
        self.items_table.setHorizontalHeaderLabels(
            [
                _t("refund.header_product"),
                _t("refund.header_qty"),
                _t("refund.header_unit_price"),
                _t("refund.header_subtotal"),
            ]
        )
        align_numeric_headers(self.items_table, (1, 2, 3))
        self.lbl_reason.setText(_t("refund.reason_label"))
        self.txt_reason.setPlaceholderText(_t("refund.reason_placeholder"))
        self.btn_refund.setText(_t("refund.btn_process"))
        self.btn_cancel.setText(_t("refund.btn_cancel"))

    def lookup_sale(self) -> None:
        """Look up original sale by document number."""
        search = self.search_input.text().strip()
        if not search:
            return

        from datetime import datetime, timedelta

        # Search in last 365 days
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=365)

        results = SaleQueryService.get_sales_history(
            from_date=from_dt,
            to_date=to_dt,
            search_term=search,
            limit=1,
        )

        if not results:
            QMessageBox.warning(self, _t("refund.not_found_title"), _t("refund.not_found_message", search=search))
            self.found_sale = None
            self.btn_refund.setEnabled(False)
            return

        sale = results[0]
        self.found_sale = sale

        # Display sale info
        customer_name = sale.customer.name if sale.customer else _t("refund.walk_in")
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        self.lbl_sale_info.setText(
            f"{_t('refund.receipt_label')} {sale.document_number} | "
            f"{_t('common.date')}: {date_str} | "
            f"{_t('refund.customer_label')}: {customer_name} | "
            f"{_t('common.total')}: {format_currency(sale.total_amount)} | "
            f"{_t('common.status')}: {sale.status}"
        )

        # Populate items table
        self.items_table.setRowCount(0)
        for item in sale.items:
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)

            product_name = item.product.name_en if item.product else _t("refund.unknown_product")
            self.items_table.setItem(row, 0, QTableWidgetItem(product_name))

            qty_item = QTableWidgetItem(str(item.qty))
            qty_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.items_table.setItem(row, 1, qty_item)

            price_item = QTableWidgetItem(format_currency(item.unit_price))
            price_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.items_table.setItem(row, 2, price_item)

            subtotal_item = QTableWidgetItem(format_currency(item.subtotal))
            subtotal_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.items_table.setItem(row, 3, subtotal_item)

        # Enable refund button only for valid sales
        can_refund = sale.status not in ("VOID", "REFUNDED") and sale.payment_method != "REFUND"
        self.btn_refund.setEnabled(can_refund)

        if not can_refund:
            QMessageBox.warning(
                self,
                _t("refund.cannot_refund_title"),
                _t("refund.cannot_refund_message", reason=sale.status),
            )

    def process_refund(self) -> None:
        """Process the refund after permission check."""
        if not self.found_sale:
            return

        reason = self.txt_reason.toPlainText().strip()
        if not reason:
            QMessageBox.warning(self, _t("common.validation_error"), _t("refund.reason_required"))
            return

        # Permission check
        from cbpos.core.constants.permissions import Permissions

        authorized_user = check_permission_with_override(Permissions.SALES_REFUND, self)
        if not authorized_user:
            return

        # Confirm -- spelling out what is handed back vs. taken off credit (#715)
        breakdown = TransactionService.refund_breakdown(self.found_sale.id)
        if breakdown is None:
            QMessageBox.warning(self, _t("refund.not_found_title"), _t("refund.not_found_message"))
            return
        doc_number = self.found_sale.document_number
        reply = QMessageBox.question(
            self,
            _t("refund.confirm_title"),
            refund_confirm_text(doc_number, breakdown, reason),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_refund.setEnabled(False)
        self.btn_refund.setText(_t("refund.processing"))
        try:
            success = TransactionService.process_refund(
                original_sale_id=self.found_sale.id,
                refund_reason=reason,
                user_id=authorized_user.id,
            )
            if success:
                QMessageBox.information(
                    self,
                    _t("refund.success_title"),
                    refund_done_text(doc_number, breakdown),
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self, _t("common.error"), _t("refund.failed_message", error=_t("common.unknown_error"))
                )
                self.btn_refund.setText(_t("refund.btn_process"))
                self.btn_refund.setEnabled(True)
        except ValueError as e:
            QMessageBox.warning(self, _t("common.validation_error"), str(e))
            self.btn_refund.setText(_t("refund.btn_process"))
            self.btn_refund.setEnabled(True)
        except Exception as e:
            logger.error("Refund failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), _t("refund.error_message", error=str(e)))
            self.btn_refund.setText(_t("refund.btn_process"))
            self.btn_refund.setEnabled(True)
