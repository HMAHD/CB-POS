"""Read-only dialog showing stock count variance report."""

from decimal import Decimal

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGridLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.stock_count_service import StockCountService
from cbpos.core.utils.formatters import (
    format_currency,
    format_document_status,
    format_quantity,
    format_signed,
)
from cbpos.i18n import _t
from cbpos.ui.constants import SPACING_XL, SPACING_XS
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, NEUTRAL, SUCCESS, status_color
from cbpos.ui.utils.layout_helpers import protect_vertical_sizing
from cbpos.ui.widgets.dialog_footer import make_close_footer
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    configure_table_columns,
)

# Expected, Counted, Variance, Value -- cells and headers right-align.
FIRST_NUMERIC_COL = 2


def _count_decimals(product) -> int:
    """Decimal places a product is counted in: its unit's, else 3 if weighed, else 0."""
    if product is None:
        return 0
    if product.unit is not None:
        return min(product.unit.decimal_places or 0, 3)
    return 3 if product.is_weighted else 0


def _format_count(qty, product) -> str:
    """A count in its product's unit: ``12`` for pieces, ``1.250`` for kg; "" if not counted yet."""
    if qty is None:
        return ""
    return format_quantity(qty, _count_decimals(product))


def _format_variance(qty, product) -> str:
    """A variance with an explicit sign (+3 / -3), so it doesn't rely on colour alone (#559)."""
    if qty is None:
        return ""
    return format_signed(qty, lambda value: _format_count(value, product))


def _variance_meaning(value) -> str:
    """Shortage is danger, surplus success, none neutral."""
    if value < 0:
        return DANGER
    return SUCCESS if value > 0 else NEUTRAL


def _format_net(value: Decimal) -> str:
    """Net variance as signed money: +Rs. 500.00 / -Rs. 500.00 / Rs. 0.00."""
    return format_signed(value, format_currency)


class StockCountReportDialog(QDialog):
    """Read-only dialog showing stock count variance report."""

    def __init__(self, stock_count_id: int, parent=None):
        """Initialize the dialog and build the report for the given stock count."""
        super().__init__(parent)
        self.setWindowTitle(_t("stock_take.report_title"))
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        self.init_ui(stock_count_id)

    def init_ui(self, stock_count_id: int) -> None:
        """Build the header info and read-only items table for the report."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        stock_count = StockCountService.get_stock_count(stock_count_id)
        if not stock_count:
            layout.addWidget(QLabel(_t("stock_take.count_not_found")))
            return

        # Header
        title = QLabel(_t("stock_take.count_label", number=stock_count.document_number))
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Header info grid (label/value pairs with 24px gaps, UI-019)
        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(SPACING_XL)
        info_grid.setVerticalSpacing(SPACING_XS)
        info_grid.setContentsMargins(0, 4, 0, 8)

        lbl_status_key = QLabel(_t("common.status"))
        lbl_status_key.setProperty("class", "muted")
        lbl_status_val = QLabel(format_document_status(stock_count.status) if stock_count.status else _t("common.na"))
        lbl_status_val.setProperty("class", "bold")

        lbl_date_key = QLabel(_t("common.date"))
        lbl_date_key.setProperty("class", "muted")
        date_str = stock_count.date.strftime("%Y-%m-%d %H:%M") if stock_count.date else _t("common.na")
        lbl_date_val = QLabel(date_str)
        lbl_date_val.setProperty("class", "bold")

        lbl_note_key = QLabel(_t("common.notes"))
        lbl_note_key.setProperty("class", "muted")
        lbl_note_val = QLabel(stock_count.note or _t("common.na"))
        lbl_note_val.setProperty("class", "bold")

        # Net variance and total discrepancy, same labels as the stats bar (#644)
        totals = StockCountService.variance_totals(stock_count.items)
        self.lbl_net_variance_key = QLabel(_t("stock_take.net_variance"))
        self.lbl_net_variance_key.setProperty("class", "muted")
        self.lbl_net_variance_key.setToolTip(_t("stock_take.net_variance_hint"))
        self.lbl_net_variance_val = QLabel(_format_net(totals.net))
        self.lbl_net_variance_val.setProperty("status", _variance_meaning(totals.net))
        self.lbl_net_variance_val.setProperty("class", "bold")
        self.lbl_discrepancy_key = QLabel(_t("stock_take.total_discrepancy"))
        self.lbl_discrepancy_key.setProperty("class", "muted")
        self.lbl_discrepancy_key.setToolTip(_t("stock_take.total_discrepancy_hint"))
        self.lbl_discrepancy_val = QLabel(format_currency(totals.discrepancy))
        self.lbl_discrepancy_val.setProperty("class", "bold")

        info_grid.addWidget(lbl_status_key, 0, 0)
        info_grid.addWidget(lbl_status_val, 1, 0)
        info_grid.addWidget(lbl_date_key, 0, 1)
        info_grid.addWidget(lbl_date_val, 1, 1)
        info_grid.addWidget(lbl_note_key, 0, 2)
        info_grid.addWidget(lbl_note_val, 1, 2)
        info_grid.addWidget(self.lbl_net_variance_key, 0, 3)
        info_grid.addWidget(self.lbl_net_variance_val, 1, 3)
        info_grid.addWidget(self.lbl_discrepancy_key, 0, 4)
        info_grid.addWidget(self.lbl_discrepancy_val, 1, 4)
        info_grid.setColumnStretch(2, 1)
        layout.addLayout(info_grid)

        # Items table
        table = QTableWidget()
        self.table = table
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(
            [
                _t("stock_take.col_barcode"),
                _t("stock_take.col_product"),
                _t("stock_take.col_expected"),
                _t("stock_take.col_counted"),
                _t("stock_take.col_variance"),
                _t("stock_take.col_value"),
            ]
        )
        align_numeric_headers(table, range(FIRST_NUMERIC_COL, 6))
        configure_table_columns(
            table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # Barcode
                1: QHeaderView.ResizeMode.Stretch,  # Product - needs the room
                2: QHeaderView.ResizeMode.ResizeToContents,  # Expected
                3: QHeaderView.ResizeMode.ResizeToContents,  # Counted
                4: QHeaderView.ResizeMode.ResizeToContents,  # Variance
                5: QHeaderView.ResizeMode.ResizeToContents,  # Value
            },
            minimum_section_size=70,
        )
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        attach_table_empty_state(table, Icons.STOCK_TAKE, "common.no_items")

        for item in stock_count.items:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(item.product.barcode if item.product else ""))
            table.setItem(
                row,
                1,
                QTableWidgetItem(item.product.display_name if item.product else _t("stock_take.unknown_product")),
            )

            for col, val in [
                (2, item.expected_qty),
                (3, item.counted_qty),
                (4, item.variance_qty),
            ]:
                text = _format_variance(val, item.product) if col == 4 else _format_count(val, item.product)
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(NUMERIC_ALIGNMENT)
                if col == 4 and val is not None:
                    cell.setForeground(status_color(_variance_meaning(val)))
                table.setItem(row, col, cell)

            val_text = format_signed(item.variance_value, format_currency) if item.variance_value is not None else ""
            val_cell = QTableWidgetItem(val_text)
            val_cell.setTextAlignment(NUMERIC_ALIGNMENT)
            if item.variance_value is not None:
                val_cell.setForeground(status_color(_variance_meaning(item.variance_value)))
            table.setItem(row, 5, val_cell)

        layout.addWidget(table, 1)

        close_layout, self.close_btn = make_close_footer(
            close_key="common.close",
            on_close=self.accept,
            close_object_name="BtnCancel",
        )
        self.close_btn.setAutoDefault(False)
        layout.addLayout(close_layout)
        protect_vertical_sizing(self)
