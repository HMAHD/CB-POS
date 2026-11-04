"""
Refund Dialog — item-level returns and partial refunds (#812).

Master-detail view of original sale items with:
- Item-level return quantity spinboxes (supports weighed items with 3 decimals)
- Item-level reason presets
- "Return all remaining" button (Alt+A)
- Live preview strip for total refund, tax breakdown, and tender distribution
- Manager override to redirect tender to CASH or CUSTOMER_CREDIT
"""

import logging
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind
from cbpos.core.services.refund_breakdown import RefundBreakdown
from cbpos.core.services.refund_service import (
    RefundLineRequest,
    RefundPreview,
    RefundService,
)
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency, format_datetime
from cbpos.core.utils.permission_helper import check_permission_with_override
from cbpos.i18n import _t
from cbpos.ui.refund_messages import refund_confirm_text, refund_done_text
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)

logger = logging.getLogger(__name__)


class RefundTenderOverrideDialog(QDialog):
    """Dialog for managers to override tender allocation to CASH or CREDIT."""

    def __init__(self, parent=None, has_customer: bool = False):
        super().__init__(parent)
        self.setWindowTitle(_t("refund.override_title"))
        self.setMinimumWidth(400)
        self.has_customer = has_customer
        self.selected_tender = "CASH"
        self.override_reason = ""
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl_tender = QLabel(_t("refund.override_tender_label"))
        lbl_tender.setProperty("class", "bold")
        layout.addWidget(lbl_tender)

        self.btn_group = QButtonGroup(self)
        self.rb_cash = QRadioButton(_t("refund.tender_cash"))
        self.rb_cash.setChecked(True)
        self.btn_group.addButton(self.rb_cash)
        layout.addWidget(self.rb_cash)

        self.rb_credit = QRadioButton(_t("refund.tender_credit"))
        self.rb_credit.setEnabled(self.has_customer)
        if not self.has_customer:
            self.rb_credit.setToolTip(_t("refund.credit_override_needs_customer"))
        self.btn_group.addButton(self.rb_credit)
        layout.addWidget(self.rb_credit)

        lbl_reason = QLabel(_t("refund.override_reason_label"))
        lbl_reason.setProperty("class", "bold")
        layout.addWidget(lbl_reason)

        self.txt_reason = QLineEdit()
        self.txt_reason.setPlaceholderText(_t("refund.override_reason_placeholder"))
        layout.addWidget(self.txt_reason)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_apply = QPushButton(_t("refund.override_btn_apply"))
        self.btn_apply.setProperty("class", "primary")
        self.btn_apply.clicked.connect(self._on_apply)
        btn_box.addWidget(self.btn_apply)

        self.btn_cancel = QPushButton(_t("refund.btn_cancel"))
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

    def _on_apply(self) -> None:
        reason = self.txt_reason.text().strip()
        if not reason:
            QMessageBox.warning(self, _t("common.validation_error"), _t("refund.override_reason_label"))
            self.txt_reason.setFocus()
            return
        self.selected_tender = "CREDIT" if self.rb_credit.isChecked() else "CASH"
        self.override_reason = reason
        self.accept()


class RefundDialog(QDialog):
    """Dialog for partial and full item-level refunds (#812)."""

    def __init__(self, parent=None, sale=None):
        super().__init__(parent)
        self.setWindowTitle(_t("refund.title"))
        self.setMinimumSize(850, 580)
        self.resize(900, 620)
        self.setObjectName("RefundDialog")

        self.found_sale = None
        self._refundable_lines: list = []
        self._spinboxes: list[QSpinBox | QDoubleSpinBox] = []
        self._combos: list[QComboBox] = []
        self._val_labels: list[QLabel] = []
        self._current_preview: RefundPreview | None = None

        self._tender_override: str | None = None
        self._override_reason: str | None = None

        self._init_ui()
        if sale:
            self.load_sale(sale)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 1. Search Bar
        search_layout = QHBoxLayout()
        self.lbl_receipt = QLabel(_t("refund.receipt_label"))
        self.lbl_receipt.setProperty("class", "bold")
        search_layout.addWidget(self.lbl_receipt)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_t("refund.receipt_placeholder"))
        self.search_input.returnPressed.connect(self.lookup_sale)
        search_layout.addWidget(self.search_input, 1)

        self.btn_lookup = QPushButton(_t("refund.btn_lookup"))
        self.btn_lookup.setProperty("class", "primary")
        self.btn_lookup.clicked.connect(self.lookup_sale)
        search_layout.addWidget(self.btn_lookup)
        layout.addLayout(search_layout)

        # 2. Sale Info Header Strip
        self.lbl_sale_info = QLabel(_t("refund.no_sale_loaded"))
        self.lbl_sale_info.setProperty("class", "info-banner")
        layout.addWidget(self.lbl_sale_info)

        # Status banner (for fully refunded / voided warning)
        self.lbl_status_banner = QLabel("")
        self.lbl_status_banner.setProperty("class", "warning-banner")
        self.lbl_status_banner.setVisible(False)
        layout.addWidget(self.lbl_status_banner)

        # 3. Items Table
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(6)
        self.items_table.setHorizontalHeaderLabels(
            [
                _t("refund.header_product"),
                _t("refund.col_sold"),
                _t("refund.col_refunded"),
                _t("refund.col_return_qty"),
                _t("refund.col_value"),
                _t("refund.col_reason"),
            ]
        )
        configure_table_columns(
            self.items_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
                5: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        align_numeric_headers(self.items_table, (1, 2, 3, 4))
        attach_table_empty_state(self.items_table, Icons.SALES, "common.no_items")
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.setAlternatingRowColors(True)
        layout.addWidget(self.items_table, 1)

        # 4. Table Controls Strip (Return all remaining)
        table_controls = QHBoxLayout()
        self.btn_return_all = QPushButton(_t("refund.return_all"))
        self.btn_return_all.setShortcut("Alt+A")
        self.btn_return_all.setProperty("class", "secondary")
        self.btn_return_all.setEnabled(False)
        self.btn_return_all.clicked.connect(self._on_return_all)
        table_controls.addWidget(self.btn_return_all)
        table_controls.addStretch()
        layout.addLayout(table_controls)

        # 5. Live Preview Summary Group
        self.preview_group = QGroupBox(_t("refund.total"))
        preview_layout = QVBoxLayout(self.preview_group)
        preview_layout.setSpacing(6)

        self.lbl_refund_total = QLabel(f"{_t('refund.total')}: {format_currency(Decimal('0.00'))}")
        self.lbl_refund_total.setProperty("class", "bold")
        preview_layout.addWidget(self.lbl_refund_total)

        give_back_box = QHBoxLayout()
        self.lbl_give_back = QLabel(f"{_t('refund.give_back')}: —")
        give_back_box.addWidget(self.lbl_give_back, 1)

        self.btn_change_tender = QPushButton(_t("refund.change_tender"))
        self.btn_change_tender.setProperty("class", "secondary")
        self.btn_change_tender.setEnabled(False)
        self.btn_change_tender.clicked.connect(self._on_change_tender)
        give_back_box.addWidget(self.btn_change_tender)
        preview_layout.addLayout(give_back_box)

        layout.addWidget(self.preview_group)

        # 6. Overall Reason Input
        reason_layout = QHBoxLayout()
        self.lbl_reason = QLabel(_t("refund.reason_label"))
        self.lbl_reason.setProperty("class", "bold")
        reason_layout.addWidget(self.lbl_reason)

        self.txt_reason = QLineEdit()
        self.txt_reason.setPlaceholderText(_t("refund.reason_placeholder"))
        # Backwards compatibility helpers
        self.txt_reason.toPlainText = self.txt_reason.text
        self.txt_reason.setPlainText = self.txt_reason.setText
        reason_layout.addWidget(self.txt_reason, 1)
        layout.addLayout(reason_layout)

        # 7. Action Buttons Footer
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_refund = QPushButton(_t("refund.primary", amount=format_currency(Decimal("0.00"))))
        self.btn_refund.setProperty("class", "danger")
        self.btn_refund.setEnabled(False)
        self.btn_refund.clicked.connect(self.process_refund)
        btn_layout.addWidget(self.btn_refund)

        self.btn_cancel = QPushButton(_t("refund.btn_cancel"))
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("refund.title"))
        self.lbl_receipt.setText(_t("refund.receipt_label"))
        self.search_input.setPlaceholderText(_t("refund.receipt_placeholder"))
        self.btn_lookup.setText(_t("refund.btn_lookup"))
        self.btn_return_all.setText(_t("refund.return_all"))
        self.preview_group.setTitle(_t("refund.total"))
        self.btn_change_tender.setText(_t("refund.change_tender"))
        self.lbl_reason.setText(_t("refund.reason_label"))
        self.txt_reason.setPlaceholderText(_t("refund.reason_placeholder"))
        self.btn_cancel.setText(_t("refund.btn_cancel"))

        self.items_table.setHorizontalHeaderLabels(
            [
                _t("refund.header_product"),
                _t("refund.col_sold"),
                _t("refund.col_refunded"),
                _t("refund.col_return_qty"),
                _t("refund.col_value"),
                _t("refund.col_reason"),
            ]
        )
        align_numeric_headers(self.items_table, (1, 2, 3, 4))
        self._recalculate()

    def lookup_sale(self) -> None:
        """Look up original sale by document number."""
        search = self.search_input.text().strip()
        if not search:
            return

        from datetime import datetime, timedelta

        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=365)

        results = SaleQueryService.get_sales_history(
            from_date=from_dt,
            to_date=to_dt,
            search_term=search,
            limit=1,
        )

        if not results:
            QMessageBox.warning(self, _t("refund.not_found_title"), _t("refund.not_found_message"))
            self.found_sale = None
            self.btn_refund.setEnabled(False)
            return

        self.load_sale(results[0])

    def load_sale(self, sale) -> None:
        """Load a sale instance into the dialog and initialize rows."""
        if not sale:
            return
        self.found_sale = sale
        self._tender_override = None
        self._override_reason = None

        if getattr(sale, "document_number", None):
            self.search_input.setText(str(sale.document_number))

        # Check document validity & status
        is_void = getattr(sale, "status", "") == DocumentStatus.VOID
        is_refund_doc = getattr(sale, "payment_method", "") == "REFUND" or getattr(sale, "refund_of_sale_id", None)
        refund_state = RefundService.refund_state(sale.id)

        customer_name = sale.customer.name if getattr(sale, "customer", None) else _t("refund.walk_in")
        date_str = format_datetime(sale.date) if getattr(sale, "date", None) else "N/A"
        self.lbl_sale_info.setText(
            f"{_t('refund.receipt_label')} {sale.document_number} · "
            f"{date_str} · "
            f"{customer_name} · "
            f"{_t('common.total')}: {format_currency(sale.total_amount)}"
        )

        # Status banners
        if is_void:
            self.lbl_status_banner.setText("This sale was voided and can't be refunded.")
            self.lbl_status_banner.setVisible(True)
        elif is_refund_doc:
            self.lbl_status_banner.setText("Refund documents cannot be refunded.")
            self.lbl_status_banner.setVisible(True)
        elif refund_state == "FULL":
            self.lbl_status_banner.setText(_t("refund.fully_refunded"))
            self.lbl_status_banner.setVisible(True)
        else:
            self.lbl_status_banner.setVisible(False)

        # Fetch refundable lines
        self._refundable_lines = RefundService.refundable_lines(sale.id)
        self._populate_table()

        can_refund = not is_void and not is_refund_doc and refund_state != "FULL"
        self.btn_return_all.setEnabled(can_refund)
        self.btn_change_tender.setEnabled(can_refund)
        self._recalculate()

    def _populate_table(self) -> None:
        """Populate the table with refundable items and quantity spinboxes."""
        self.items_table.setRowCount(0)
        self._spinboxes.clear()
        self._combos.clear()
        self._val_labels.clear()

        reasons = [
            _t("refund.reason_damaged"),
            _t("refund.reason_wrong_item"),
            _t("refund.reason_customer_mind"),
            _t("refund.reason_expired"),
            _t("refund.reason_other"),
        ]

        with batch_table_update(self.items_table):
            for line in self._refundable_lines:
                row = self.items_table.rowCount()
                self.items_table.insertRow(row)

                # Col 0: Item
                self.items_table.setItem(row, 0, QTableWidgetItem(line.product_name))

                # Col 1: Sold
                sold_str = f"{line.sold_qty:.3f}" if line.is_weighed else str(int(line.sold_qty))
                sold_item = QTableWidgetItem(sold_str)
                sold_item.setTextAlignment(NUMERIC_ALIGNMENT)
                self.items_table.setItem(row, 1, sold_item)

                # Col 2: Refunded
                ref_str = f"{line.refunded_qty:.3f}" if line.is_weighed else str(int(line.refunded_qty))
                ref_item = QTableWidgetItem(ref_str)
                ref_item.setTextAlignment(NUMERIC_ALIGNMENT)
                self.items_table.setItem(row, 2, ref_item)

                # Col 3: Return qty (Spinbox or '—')
                if line.remaining_qty > Decimal("0.000"):
                    if line.is_weighed:
                        sb = QDoubleSpinBox()
                        sb.setDecimals(3)
                        sb.setSingleStep(0.100)
                        sb.setRange(0.000, float(line.remaining_qty))
                    else:
                        sb = QSpinBox()
                        sb.setRange(0, int(line.remaining_qty))
                    sb.setAlignment(Qt.AlignmentFlag.AlignRight)
                    sb.valueChanged.connect(self._recalculate)
                    self._spinboxes.append(sb)
                    self.items_table.setCellWidget(row, 3, sb)
                else:
                    self._spinboxes.append(None)
                    dash_item = QTableWidgetItem("—")
                    dash_item.setTextAlignment(NUMERIC_ALIGNMENT)
                    self.items_table.setItem(row, 3, dash_item)

                # Col 4: Value (Live Label or '—')
                if line.remaining_qty > Decimal("0.000"):
                    val_lbl = QLabel(format_currency(Decimal("0.00")))
                    val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self._val_labels.append(val_lbl)
                    self.items_table.setCellWidget(row, 4, val_lbl)
                else:
                    self._val_labels.append(None)
                    dash_val = QTableWidgetItem("—")
                    dash_val.setTextAlignment(NUMERIC_ALIGNMENT)
                    self.items_table.setItem(row, 4, dash_val)

                # Col 5: Reason (Combo or '(refunded)')
                if line.remaining_qty > Decimal("0.000"):
                    cb = QComboBox()
                    cb.addItems(reasons)
                    self._combos.append(cb)
                    self.items_table.setCellWidget(row, 5, cb)
                else:
                    self._combos.append(None)
                    ref_tag = QTableWidgetItem(_t("refund.line_refunded"))
                    ref_tag.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    ref_tag.setForeground(Qt.GlobalColor.gray)
                    self.items_table.setItem(row, 5, ref_tag)

    def _on_return_all(self) -> None:
        """Fill all remaining quantities into spinboxes (Alt+A)."""
        for i, sb in enumerate(self._spinboxes):
            if sb is not None:
                rem = self._refundable_lines[i].remaining_qty
                if isinstance(sb, QDoubleSpinBox):
                    sb.setValue(float(rem))
                else:
                    sb.setValue(int(rem))
        self._recalculate()

    def _collect_requests(self) -> list[RefundLineRequest]:
        """Collect non-zero return requests from the table."""
        requests = []
        for i, sb in enumerate(self._spinboxes):
            if sb is not None and sb.value() > 0:
                line = self._refundable_lines[i]
                qty = Decimal(str(sb.value()))
                combo = self._combos[i]
                reason = combo.currentText() if combo else None
                requests.append(RefundLineRequest(sale_item_id=line.sale_item_id, qty=qty, reason=reason))
        return requests

    def _recalculate(self) -> None:
        """Recalculate preview values from current spinbox quantities."""
        if not self.found_sale:
            return

        requests = self._collect_requests()
        if not requests:
            self._current_preview = None
            for lbl in self._val_labels:
                if lbl is not None:
                    lbl.setText(format_currency(Decimal("0.00")))
            self.lbl_refund_total.setText(f"{_t('refund.total')}: {format_currency(Decimal('0.00'))}")
            self.lbl_give_back.setText(f"{_t('refund.give_back')}: —")
            self.btn_refund.setText(_t("refund.primary", amount=format_currency(Decimal("0.00"))))
            self.btn_refund.setEnabled(False)
            return

        try:
            preview = RefundService.preview(
                self.found_sale.id,
                requests,
                tender_override=self._tender_override,
                override_reason=self._override_reason,
            )
            self._current_preview = preview

            # Update line value labels
            req_index = 0
            for i, sb in enumerate(self._spinboxes):
                lbl = self._val_labels[i]
                if sb is not None and lbl is not None:
                    if sb.value() > 0:
                        line_val = preview.lines[req_index].refund_value
                        lbl.setText(format_currency(line_val))
                        req_index += 1
                    else:
                        lbl.setText(format_currency(Decimal("0.00")))

            # Summary strip
            vat_note = f" (VAT incl. {format_currency(preview.refund_vat)})" if preview.refund_vat > 0 else ""
            self.lbl_refund_total.setText(
                f"{_t('refund.total')}  {format_currency(preview.total_refund_amount)}{vat_note}"
            )

            # Tender give back display
            give_back_parts = []
            for t in preview.tenders:
                if t.kind == PaymentMethodKind.CASH:
                    give_back_parts.append(f"{_t('refund.tender_cash')} {format_currency(t.amount)}")
                elif t.kind == PaymentMethodKind.CREDIT:
                    give_back_parts.append(f"{_t('refund.tender_credit')} -{format_currency(t.amount)}")
                elif t.note:
                    give_back_parts.append(t.note)
                else:
                    give_back_parts.append(f"{t.payment_method} {format_currency(t.amount)}")

            give_back_text = " · ".join(give_back_parts) if give_back_parts else "—"
            if self._tender_override:
                give_back_text += f" [Overridden: {self._tender_override}]"
            self.lbl_give_back.setText(f"{_t('refund.give_back')}:  {give_back_text}")

            # Primary button
            self.btn_refund.setText(_t("refund.primary", amount=format_currency(preview.total_refund_amount)))
            self.btn_refund.setEnabled(preview.total_refund_amount > Decimal("0.00"))

        except Exception as e:
            logger.error("Preview failed: %s", e)
            self.btn_refund.setEnabled(False)

    def _on_change_tender(self) -> None:
        """Handle manager override of tender allocation."""
        if not self.found_sale:
            return

        authorized_user = check_permission_with_override(Permissions.SALES_REFUND_OVERRIDE_TENDER, self)
        if not authorized_user:
            return

        dlg = RefundTenderOverrideDialog(self, has_customer=bool(self.found_sale.customer_id))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._tender_override = dlg.selected_tender
            self._override_reason = dlg.override_reason
            self._recalculate()

    def process_refund(self) -> None:
        """Process the refund after permission check and confirmation."""
        if not self.found_sale:
            return

        reason = self.txt_reason.text().strip()
        if not reason:
            # Check table combos
            first_combo = next((c.currentText() for c in self._combos if c), None)
            reason = first_combo or "Customer return"

        # Permission check
        authorized_user = check_permission_with_override(Permissions.SALES_REFUND, self)
        if not authorized_user:
            return

        requests = self._collect_requests()
        if not requests:
            # Fallback for callers setting found_sale without spinbox interaction
            refundable = RefundService.refundable_lines(self.found_sale.id)
            requests = [
                RefundLineRequest(sale_item_id=line.sale_item_id, qty=line.remaining_qty, reason=reason)
                for line in refundable
                if line.remaining_qty > Decimal("0.000")
            ]
        if not requests:
            QMessageBox.warning(self, _t("common.warning"), _t("refund.fully_refunded"))
            return

        # Confirmation question
        doc_number = self.found_sale.document_number
        breakdown = TransactionService.refund_breakdown(self.found_sale.id) or RefundBreakdown(
            total=self._current_preview.total_refund_amount if self._current_preview else Decimal("0.00"),
            cash_back=Decimal("0.00"),
            credit_reversed=Decimal("0.00"),
            customer_name=self.found_sale.customer.name if self.found_sale.customer else "",
        )

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
            RefundService.refund(
                sale_id=self.found_sale.id,
                lines=requests,
                reason=reason,
                user_id=authorized_user.id,
                tender_override=self._tender_override,
                override_reason=self._override_reason,
            )

            QMessageBox.information(
                self,
                _t("refund.success_title"),
                refund_done_text(doc_number, breakdown),
            )
            self.accept()

        except ValueError as e:
            QMessageBox.warning(self, _t("common.validation_error"), translate_error(str(e)))
            self.btn_refund.setText(_t("refund.btn_process"))
            self.btn_refund.setEnabled(True)
        except Exception as e:
            logger.error("Refund failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), _t("refund.error_message", error=translate_error(str(e))))
            self.btn_refund.setText(_t("refund.btn_process"))
            self.btn_refund.setEnabled(True)
