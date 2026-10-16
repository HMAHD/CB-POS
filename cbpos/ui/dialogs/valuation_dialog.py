from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.report_service import ReportService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.ui.resources.status_colors import DANGER, SUCCESS, status_color


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
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setObjectName("ValuationTable")
        layout.addWidget(self.table)

        # Close Button
        btn_close = QPushButton(_t("common.close"))
        btn_close.setProperty("class", "secondary")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

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
        self.table.setRowCount(len(breakdown))

        for row, item in enumerate(breakdown):
            # Category
            self.table.setItem(row, 0, QTableWidgetItem(item["category"]))

            # Product Count
            count_item = QTableWidgetItem(str(item["product_count"]))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, count_item)

            # Cost Value
            cost_item = QTableWidgetItem(format_currency(item["cost_value"]))
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, cost_item)

            # Retail Value
            retail_item = QTableWidgetItem(format_currency(item["retail_value"]))
            retail_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, retail_item)

            # Profit
            profit_item = QTableWidgetItem(format_currency(item["profit"]))
            profit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Color based on profit
            if item["profit"] >= 0:
                profit_item.setForeground(status_color(SUCCESS))
            else:
                profit_item.setForeground(status_color(DANGER))

            self.table.setItem(row, 4, profit_item)
