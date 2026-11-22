"""Dialog to inspect, write off, or discount expiring and expired product batches (#926)."""

from datetime import date, timedelta
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.models import ProductBatch
from cbpos.core.services.batch_service import BatchService
from cbpos.core.utils.formatters import format_currency, format_quantity
from cbpos.i18n import _t
from cbpos.ui.dialogs.stock_adjustment_dialog import StockAdjustmentDialog
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.table_helpers import NUMERIC_ALIGNMENT


class ExpiringBatchesDialog(QDialog):
    """Dialog displaying batches approaching expiry or already expired, with action buttons."""

    def __init__(self, parent=None, initial_tab: str = "30"):
        super().__init__(parent)
        self.setObjectName("ExpiringBatchesDialog")
        self.setWindowTitle(_t("expiring_batches.title", default="Expiring & Expired Batches"))
        self.setMinimumSize(780, 480)
        self.resize(840, 520)

        self._current_filter: str = initial_tab
        self._batches: list[ProductBatch] = []

        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Tab bar
        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("TabBarExpiring")
        self.tab_bar.addTab(_t("expiring_batches.tab_30_days", default="< 30 Days"))
        self.tab_bar.addTab(_t("expiring_batches.tab_60_days", default="< 60 Days"))
        self.tab_bar.addTab(_t("expiring_batches.tab_90_days", default="< 90 Days"))
        self.tab_bar.addTab(_t("expiring_batches.tab_expired", default="Expired"))
        tab_map = {"30": 0, "60": 1, "90": 2, "expired": 3}
        self.tab_bar.setCurrentIndex(tab_map.get(self._current_filter, 0))
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_bar)

        # Table
        self.table = QTableWidget()
        self.table.setObjectName("TblExpiringBatches")
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                _t("expiring_batches.col_product", default="Product"),
                _t("expiring_batches.col_batch_no", default="Batch No"),
                _t("expiring_batches.col_expiry", default="Expiry Date"),
                _t("expiring_batches.col_mrp", default="MRP"),
                _t("expiring_batches.col_qty", default="Qty on Hand"),
                _t("expiring_batches.col_status", default="Status"),
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # Actions toolbar
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_write_off = QPushButton(_t("expiring_batches.btn_write_off", default="Write-off / Mark Expired"))
        self.btn_write_off.setObjectName("BtnWriteOffExpired")
        self.btn_write_off.setEnabled(False)
        self.btn_write_off.clicked.connect(self._on_write_off)
        action_layout.addWidget(self.btn_write_off)

        self.btn_clearance = QPushButton(_t("expiring_batches.btn_clearance", default="Discount / Clearance"))
        self.btn_clearance.setObjectName("BtnClearancePriceBoard")
        self.btn_clearance.clicked.connect(self._on_clearance)
        action_layout.addWidget(self.btn_clearance)

        self.btn_supplier_return = QPushButton(_t("expiring_batches.btn_supplier_return", default="Return to Supplier"))
        self.btn_supplier_return.setObjectName("BtnSupplierReturn")
        self.btn_supplier_return.setEnabled(False)
        self.btn_supplier_return.setToolTip(
            _t(
                "expiring_batches.supplier_return_tooltip",
                default="Supplier Returns will be available in an upcoming update (#930)",
            )
        )
        action_layout.addWidget(self.btn_supplier_return)

        action_layout.addStretch()
        layout.addLayout(action_layout)

        # Footer
        footer_layout, self.btn_close, _ = make_dialog_footer(
            primary_key="common.close",
            on_primary=self.accept,
            cancel_key=None,
            primary_object_name="BtnClose",
        )
        layout.addLayout(footer_layout)

    def _on_tab_changed(self, index: int) -> None:
        modes = ["30", "60", "90", "expired"]
        if 0 <= index < len(modes):
            self._current_filter = modes[index]
            self._load_data()

    def _load_data(self) -> None:
        self._batches = BatchService.get_expiring_batches_by_filter(self._current_filter)
        self._render_table()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self._batches))
        today = date.today()
        soon_cutoff = today + timedelta(days=30)

        for row, batch in enumerate(self._batches):
            # Col 0: Product
            p_name = batch.product.name_en if batch.product else "-"
            p_barcode = batch.product.barcode if batch.product else ""
            display_p = f"{p_name} ({p_barcode})" if p_barcode else p_name
            it_p = QTableWidgetItem(display_p)
            it_p.setData(Qt.ItemDataRole.UserRole, batch)
            self.table.setItem(row, 0, it_p)

            # Col 1: Batch No
            self.table.setItem(row, 1, QTableWidgetItem(batch.batch_no or "-"))

            # Col 2: Expiry
            exp_str = batch.expiry_date.strftime("%Y-%m-%d") if batch.expiry_date else "-"
            self.table.setItem(row, 2, QTableWidgetItem(exp_str))

            # Col 3: MRP
            mrp_val = (
                batch.mrp if batch.mrp is not None else (batch.product.price if batch.product else Decimal("0.00"))
            )
            it_mrp = QTableWidgetItem(format_currency(mrp_val))
            it_mrp.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 3, it_mrp)

            # Col 4: Qty on hand
            it_qty = QTableWidgetItem(format_quantity(batch.qty_on_hand, 3))
            it_qty.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 4, it_qty)

            # Col 5: Status
            if batch.expiry_date and batch.expiry_date < today:
                status_str = _t("expiring_batches.badge_expired", default="Expired")
            elif batch.expiry_date and batch.expiry_date <= soon_cutoff:
                status_str = _t("expiring_batches.badge_expiring", default="Expiring Soon")
            else:
                status_str = _t("expiring_batches.badge_active", default="Active")
            self.table.setItem(row, 5, QTableWidgetItem(status_str))

        if self._batches:
            self.table.selectRow(0)
            self.btn_write_off.setEnabled(True)
        else:
            self.btn_write_off.setEnabled(False)

    def _on_selection_changed(self) -> None:
        curr = self.table.currentRow()
        has_sel = curr >= 0 and curr < len(self._batches)
        self.btn_write_off.setEnabled(has_sel)

    def _get_selected_batch(self) -> ProductBatch | None:
        curr = self.table.currentRow()
        if curr >= 0 and curr < len(self._batches):
            item = self.table.item(curr, 0)
            if item:
                return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_write_off(self) -> None:
        batch = self._get_selected_batch()
        if not batch or not batch.product:
            return

        dlg = StockAdjustmentDialog(
            batch.product,
            parent=self,
            batch_id=batch.id,
            default_reason="EXPIRED",
        )
        if dlg.exec():
            self._load_data()

    def _on_clearance(self) -> None:
        from cbpos.core.constants.features import Features
        from cbpos.core.services.feature_flags import feature_visible

        if feature_visible(Features.PRICE_BOARD):
            from cbpos.ui.dialogs.price_board_dialog import PriceBoardDialog

            dlg = PriceBoardDialog(parent=self)
            dlg.exec()
