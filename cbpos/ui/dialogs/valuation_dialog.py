from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.report_service import ReportService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, SUCCESS, status_color
from cbpos.ui.utils.layout_helpers import protect_vertical_sizing
from cbpos.ui.widgets.dialog_footer import make_close_footer
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)


class ValuationDialog(QDialog):
    """
    Stock Valuation Report Dialog.
    Shows total inventory value, retail value, and potential profit.
    """

    def __init__(self, parent=None):
        """Build the dialog and load the current stock valuation report."""
        super().__init__(parent)
        self.setWindowTitle(_t("valuation.title"))
        self.setObjectName("ValuationDialog")
        self.setMinimumSize(800, 600)
        self.report_service = ReportService()
        self.init_ui()
        self.load_data()

    def init_ui(self):
        """Build the summary value cards and the category breakdown table."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel(_t("valuation.title"))
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        # Cards Layout
        cards_layout = QHBoxLayout()

        # Card 1: Total Cost Value
        self.card_cost = self.create_value_card(_t("valuation.cost_value"), format_currency(0), "#003366")
        cards_layout.addWidget(self.card_cost)

        # Card 2: Total Retail Value
        self.card_retail = self.create_value_card(_t("valuation.retail_value"), format_currency(0), "#003366")
        cards_layout.addWidget(self.card_retail)

        # Card 3: Potential Profit
        self.card_profit = self.create_value_card(_t("valuation.potential_profit"), format_currency(0), "#39FF14")
        cards_layout.addWidget(self.card_profit)

        layout.addLayout(cards_layout)

        # Category Breakdown Label
        breakdown_label = QLabel(_t("valuation.breakdown"))
        breakdown_label.setObjectName("SectionTitle")
        layout.addWidget(breakdown_label)

        # Breakdown Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            [
                _t("common.category"),
                _t("valuation.col_products"),
                _t("valuation.col_cost"),
                _t("valuation.col_retail"),
                _t("valuation.col_profit"),
            ]
        )
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        align_numeric_headers(self.table.horizontalHeader(), (1, 2, 3, 4))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setObjectName("ValuationTable")
        attach_table_empty_state(self.table, Icons.INVENTORY, "common.no_items")
        layout.addWidget(self.table)

        # Close Button
        footer, self.btn_close = make_close_footer(
            close_key="common.close",
            on_close=self.close,
            close_object_name="BtnCancel",
        )
        layout.addLayout(footer)
        protect_vertical_sizing(self)

    def create_value_card(self, title: str, value: str, bg_color: str) -> QFrame:
        """Create a value display card."""
        card = QFrame()
        card.setObjectName("ValueCard")
        card.setMinimumHeight(120)

        card_layout = QVBoxLayout(card)

        # Title
        title_label = QLabel(title)
        title_label.setProperty("class", "muted")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_label)

        # Value
        value_label = QLabel(value)
        value_label.setProperty("class", "card-value")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setObjectName("value_label")
        card_layout.addWidget(value_label)

        return card

    def closeEvent(self, event):
        """Release table items on dialog close to prevent heap retention."""
        self.table.clearContents()
        self.table.setRowCount(0)
        super().closeEvent(event)

    def load_data(self):
        """Load stock valuation data."""
        data = self.report_service.get_stock_valuation()

        # Update cards
        self.card_cost.findChild(QLabel, "value_label").setText(format_currency(data["total_cost_value"]))
        self.card_retail.findChild(QLabel, "value_label").setText(format_currency(data["total_retail_value"]))

        profit_label = self.card_profit.findChild(QLabel, "value_label")
        profit_label.setText(format_currency(data["potential_profit"]))

        # Color profit based on value
        if data["potential_profit"] >= 0:
            profit_label.setProperty("class", "card-value-positive")
        else:
            profit_label.setProperty("class", "card-value-negative")

        # Update breakdown table
        breakdown = data["category_breakdown"]
        with batch_table_update(self.table):
            self.table.clearContents()
            self.table.setRowCount(0)
            self.table.setRowCount(len(breakdown))

            TableItem = QTableWidgetItem
            fmt_curr = format_currency
            num_align = NUMERIC_ALIGNMENT
            succ_color = status_color(SUCCESS)
            dang_color = status_color(DANGER)
            set_item = self.table.setItem

            for row, item in enumerate(breakdown):
                # Category
                set_item(row, 0, TableItem(item["category"]))

                # Product Count
                count_item = TableItem(str(item["product_count"]))
                count_item.setTextAlignment(num_align)
                set_item(row, 1, count_item)

                # Cost Value
                cost_item = TableItem(fmt_curr(item["cost_value"]))
                cost_item.setTextAlignment(num_align)
                set_item(row, 2, cost_item)

                # Retail Value
                retail_item = TableItem(fmt_curr(item["retail_value"]))
                retail_item.setTextAlignment(num_align)
                set_item(row, 3, retail_item)

                # Profit
                profit_item = TableItem(fmt_curr(item["profit"]))
                profit_item.setTextAlignment(num_align)

                # Color based on profit
                if item["profit"] >= 0:
                    profit_item.setForeground(succ_color)
                else:
                    profit_item.setForeground(dang_color)

                set_item(row, 4, profit_item)
