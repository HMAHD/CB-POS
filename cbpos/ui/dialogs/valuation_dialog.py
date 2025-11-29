from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.report_service import ReportService


class ValuationDialog(QDialog):
    """
    Stock Valuation Report Dialog.
    Shows total inventory value, retail value, and potential profit.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stock Valuation Report")
        self.setMinimumSize(800, 600)
        self.report_service = ReportService()
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Stock Valuation Report")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(title)

        # Cards Layout
        cards_layout = QHBoxLayout()

        # Card 1: Total Cost Value
        self.card_cost = self.create_value_card(
            "Total Stock Value (Cost)", "Rs. 0.00", "#003366"
        )
        cards_layout.addWidget(self.card_cost)

        # Card 2: Total Retail Value
        self.card_retail = self.create_value_card(
            "Total Retail Value", "Rs. 0.00", "#003366"
        )
        cards_layout.addWidget(self.card_retail)

        # Card 3: Potential Profit
        self.card_profit = self.create_value_card(
            "Potential Profit", "Rs. 0.00", "#39FF14"
        )
        cards_layout.addWidget(self.card_profit)

        layout.addLayout(cards_layout)

        # Category Breakdown Label
        breakdown_label = QLabel("Category Breakdown")
        breakdown_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: white; margin-top: 20px;"
        )
        layout.addWidget(breakdown_label)

        # Breakdown Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Category", "Products", "Cost Value", "Retail Value", "Profit"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(
            """
            QTableWidget {
                background-color: #001F3F;
                color: white;
                border: 1px solid #003366;
                gridline-color: #003366;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #003366;
                color: white;
                padding: 8px;
                border: 1px solid #001F3F;
                font-weight: bold;
            }
        """
        )
        layout.addWidget(self.table)

        # Close Button
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(
            "background-color: #003366; color: white; padding: 10px; font-weight: bold;"
        )
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def create_value_card(self, title: str, value: str, bg_color: str) -> QFrame:
        """Create a value display card."""
        card = QFrame()
        card.setStyleSheet(
            "QFrame {{ background-color: {0}; border-radius: 8px; padding: 15px; }}".format(
                bg_color
            )
        )
        card.setMinimumHeight(120)

        card_layout = QVBoxLayout(card)

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #AAAAAA; font-size: 12px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_label)

        # Value
        value_label = QLabel(value)
        value_label.setStyleSheet("color: white; font-size: 28px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setObjectName("value_label")
        card_layout.addWidget(value_label)

        return card

    def load_data(self):
        """Load stock valuation data."""
        data = self.report_service.get_stock_valuation()

        # Update cards
        self.card_cost.findChild(QLabel, "value_label").setText(
            "Rs. {0:,.2f}".format(data["total_cost_value"])
        )
        self.card_retail.findChild(QLabel, "value_label").setText(
            "Rs. {0:,.2f}".format(data["total_retail_value"])
        )

        profit_label = self.card_profit.findChild(QLabel, "value_label")
        profit_label.setText("Rs. {0:,.2f}".format(data["potential_profit"]))

        # Color profit based on value
        if data["potential_profit"] >= 0:
            profit_label.setStyleSheet(
                "color: #39FF14; font-size: 28px; font-weight: bold;"
            )
        else:
            profit_label.setStyleSheet(
                "color: #FF4136; font-size: 28px; font-weight: bold;"
            )

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
            cost_item = QTableWidgetItem("Rs. {0:,.2f}".format(item["cost_value"]))
            cost_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 2, cost_item)

            # Retail Value
            retail_item = QTableWidgetItem("Rs. {0:,.2f}".format(item["retail_value"]))
            retail_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 3, retail_item)

            # Profit
            profit_item = QTableWidgetItem("Rs. {0:,.2f}".format(item["profit"]))
            profit_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            # Color based on profit
            if item["profit"] >= 0:
                profit_item.setForeground(Qt.GlobalColor.green)
            else:
                profit_item.setForeground(Qt.GlobalColor.red)

            self.table.setItem(row, 4, profit_item)
