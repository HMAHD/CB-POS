"""Modal dialog to select a specific batch/lot when product has differing MRPs or cashier requests batch choice (#926)."""

from datetime import date, timedelta
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.models import Product, ProductBatch
from cbpos.core.services.batch_service import BatchService
from cbpos.core.utils.formatters import format_currency, format_quantity
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.table_helpers import NUMERIC_ALIGNMENT


class BatchPickerModal(QDialog):
    """Modal dialog allowing cashiers to select an active lot/batch for a tracked product."""

    def __init__(
        self,
        product: Product,
        parent=None,
        allow_expired: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("BatchPickerModal")
        self.product = product
        self.allow_expired = allow_expired
        self._selected_batch: ProductBatch | None = None
        self._all_batches: list[ProductBatch] = []

        self.setWindowTitle(_t("batch_picker.title", default="Select Batch / Lot"))
        self.setMinimumSize(540, 360)
        self.resize(560, 380)
        self._setup_ui()
        self._load_batches()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header: Product Name + Barcode
        hdr_layout = QVBoxLayout()
        hdr_layout.setSpacing(2)

        prod_name = getattr(self.product, "name_en", "") or getattr(self.product, "name", "")
        self.lbl_product = QLabel(f"<b>{prod_name}</b> ({getattr(self.product, 'barcode', '')})")
        self.lbl_product.setObjectName("LblBatchProductName")
        hdr_layout.addWidget(self.lbl_product)

        self.lbl_prompt = QLabel(
            _t(
                "batch_picker.prompt",
                name=prod_name,
                default=f"Select the batch to sell for '{prod_name}':",
            )
        )
        self.lbl_prompt.setProperty("class", "muted")
        hdr_layout.addWidget(self.lbl_prompt)
        layout.addLayout(hdr_layout)

        # Search / filter box
        self.txt_filter = QLineEdit()
        self.txt_filter.setObjectName("TxtBatchFilter")
        self.txt_filter.setPlaceholderText(_t("batch_picker.search_placeholder", default="Filter batches..."))
        self.txt_filter.textChanged.connect(self._filter_batches)
        layout.addWidget(self.txt_filter)

        # Interactive Table
        self.tbl_batches = QTableWidget()
        self.tbl_batches.setObjectName("TblBatches")
        self.tbl_batches.setColumnCount(4)
        self.tbl_batches.setHorizontalHeaderLabels(
            [
                _t("batch_picker.col_batch_no", default="Batch No"),
                _t("batch_picker.col_expiry", default="Expiry"),
                _t("batch_picker.col_mrp", default="MRP"),
                _t("batch_picker.col_qty", default="Available Qty"),
            ]
        )
        self.tbl_batches.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_batches.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl_batches.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.tbl_batches.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.tbl_batches.itemDoubleClicked.connect(self._on_double_clicked)
        self.tbl_batches.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.tbl_batches)

        # Footer
        footer_layout, self.btn_ok, self.btn_cancel = make_dialog_footer(
            primary_key="common.ok",
            on_primary=self._on_confirm,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnOk",
            cancel_object_name="BtnCancel",
        )
        self.btn_ok.setEnabled(False)
        layout.addLayout(footer_layout)

    def _load_batches(self) -> None:
        """Fetch active batches for the product and populate the table."""
        self._all_batches = BatchService.get_batches_for_product(self.product.id)
        self._render_rows(self._all_batches)

    def _render_rows(self, batches: list[ProductBatch]) -> None:
        self.tbl_batches.setRowCount(len(batches))
        today = date.today()
        soon_cutoff = today + timedelta(days=30)

        for row, batch in enumerate(batches):
            # Col 0: Batch No
            b_no = batch.batch_no or "-"
            item_no = QTableWidgetItem(b_no)
            item_no.setData(Qt.ItemDataRole.UserRole, batch)
            self.tbl_batches.setItem(row, 0, item_no)

            # Col 1: Expiry Date + Tag
            exp_str = batch.expiry_date.strftime("%Y-%m-%d") if batch.expiry_date else "-"
            if batch.expiry_date and batch.expiry_date < today:
                exp_str += f" [{_t('batch_picker.expired_badge', default='Expired')}]"
            elif batch.expiry_date and batch.expiry_date <= soon_cutoff:
                exp_str += f" [{_t('batch_picker.expiring_soon_badge', default='Expiring Soon')}]"
            item_exp = QTableWidgetItem(exp_str)
            self.tbl_batches.setItem(row, 1, item_exp)

            # Col 2: MRP
            mrp_val = batch.mrp if batch.mrp is not None else getattr(self.product, "price", Decimal("0.00"))
            item_mrp = QTableWidgetItem(format_currency(mrp_val))
            item_mrp.setTextAlignment(NUMERIC_ALIGNMENT)
            self.tbl_batches.setItem(row, 2, item_mrp)

            # Col 3: Available Qty
            qty_val = batch.qty_on_hand if batch.qty_on_hand is not None else Decimal("0.000")
            item_qty = QTableWidgetItem(format_quantity(qty_val, 3))
            item_qty.setTextAlignment(NUMERIC_ALIGNMENT)
            self.tbl_batches.setItem(row, 3, item_qty)

        if batches:
            self.tbl_batches.selectRow(0)
            self.btn_ok.setEnabled(True)
        else:
            self.btn_ok.setEnabled(False)

    def _filter_batches(self, text: str) -> None:
        search = text.strip().lower()
        if not search:
            filtered = self._all_batches
        else:
            filtered = [
                b
                for b in self._all_batches
                if (b.batch_no and search in b.batch_no.lower())
                or (b.expiry_date and search in str(b.expiry_date))
                or (b.mrp and search in str(b.mrp))
            ]
        self._render_rows(filtered)

    def _on_selection_changed(self) -> None:
        curr_row = self.tbl_batches.currentRow()
        if curr_row >= 0:
            item = self.tbl_batches.item(curr_row, 0)
            if item:
                self._selected_batch = item.data(Qt.ItemDataRole.UserRole)
                self.btn_ok.setEnabled(True)
                return
        self._selected_batch = None
        self.btn_ok.setEnabled(False)

    def _on_double_clicked(self, item: QTableWidgetItem) -> None:
        self._on_confirm()

    def _on_confirm(self) -> None:
        curr_row = self.tbl_batches.currentRow()
        if curr_row >= 0:
            item = self.tbl_batches.item(curr_row, 0)
            if item:
                self._selected_batch = item.data(Qt.ItemDataRole.UserRole)
                self.accept()
                return
        self.reject()

    def get_selected_batch(self) -> ProductBatch | None:
        """Return the confirmed selected ProductBatch, or None if cancelled."""
        return self._selected_batch

    def keyPressEvent(self, event) -> None:
        """Handle keyboard navigation: Up/Down for selection, Enter to accept, Esc to cancel."""
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._selected_batch is not None:
                self.accept()
                return
        elif key == Qt.Key.Key_Escape:
            self.reject()
            return
        elif key == Qt.Key.Key_Down:
            curr = self.tbl_batches.currentRow()
            if curr < self.tbl_batches.rowCount() - 1:
                self.tbl_batches.selectRow(curr + 1)
                return
        elif key == Qt.Key.Key_Up:
            curr = self.tbl_batches.currentRow()
            if curr > 0:
                self.tbl_batches.selectRow(curr - 1)
                return
        super().keyPressEvent(event)
