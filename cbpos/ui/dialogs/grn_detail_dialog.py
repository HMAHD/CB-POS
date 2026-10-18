"""Read-only detail view dialog for a completed GRN."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.purchase_service import PurchaseService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t


class GRNDetailDialog(QDialog):
    """Read-only detail view of a completed GRN."""

    def __init__(self, purchase_id: int, parent=None):
        """Configure the dialog window and build its read-only layout for the given purchase."""
        super().__init__(parent)
        self.setWindowTitle(_t("purchase.grn_detail_title"))
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        self.init_ui(purchase_id)

    def init_ui(self, purchase_id: int) -> None:
        """Load the purchase and render its header info, item table, and total cost."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        purchase = PurchaseService.get_purchase(purchase_id)
        if not purchase:
            layout.addWidget(QLabel(_t("purchase.purchase_not_found")))
            return

        # Header
        title = QLabel(f"{_t('purchase.grn_label')}: {purchase.document_number}")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Info row
        info_layout = QHBoxLayout()
        supplier_name = purchase.supplier.company_name if purchase.supplier else "N/A"
        info_layout.addWidget(QLabel(f"{_t('purchase.form_supplier')} {supplier_name}"))
        info_layout.addWidget(QLabel(f"{_t('purchase.form_ref')} {purchase.reference_external or 'N/A'}"))
        date_str = purchase.date.strftime("%Y-%m-%d %H:%M") if purchase.date else "N/A"
        info_layout.addWidget(QLabel(f"{_t('purchase.form_date')} {date_str}"))
        info_layout.addWidget(QLabel(f"{_t('purchase.detail_status')}: {purchase.status}"))
        info_layout.addStretch()
        layout.addLayout(info_layout)

        # Items table
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            [
                _t("purchase.detail_product"),
                _t("purchase.detail_barcode"),
                _t("purchase.detail_qty"),
                _t("purchase.detail_unit_cost"),
                _t("purchase.detail_line_total"),
            ]
        )
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for item in purchase.items:
            row = table.rowCount()
            table.insertRow(row)
            product_name = item.product.name_en if item.product else "Unknown"
            barcode = item.product.barcode if item.product else ""
            line_total = item.qty_received * item.unit_cost

            table.setItem(row, 0, QTableWidgetItem(product_name))
            table.setItem(row, 1, QTableWidgetItem(barcode))

            qty_item = QTableWidgetItem(f"{item.qty_received:.3f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 2, qty_item)

            cost_item = QTableWidgetItem(format_currency(item.unit_cost))
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 3, cost_item)

            total_item = QTableWidgetItem(format_currency(line_total))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 4, total_item)

        layout.addWidget(table, 1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        total_label = QLabel(f"{_t('purchase.total_cost_label')}: {format_currency(purchase.total_cost)}")
        total_label.setObjectName("GrnTotalLabel")
        footer.addWidget(total_label)
        layout.addLayout(footer)

        # Close button
        close_btn = QPushButton(_t("common.close"))
        close_btn.setObjectName("BtnCancel")
        close_btn.setProperty("class", "secondary")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
