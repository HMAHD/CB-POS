import logging
from decimal import Decimal

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QGridLayout,
)
from PyQt6.QtCore import Qt
from cbpos.ui.widgets.info_card import InfoCard
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # --- KPI Cards Row ---
        cards_layout = QGridLayout()
        cards_layout.setSpacing(20)

        self.card_sales = InfoCard(
            "Today's Sales",
            format_currency(0),
            "fa5s.rupee-sign",
            "Loading...",
            True,
        )
        cards_layout.addWidget(self.card_sales, 0, 0)

        self.card_transactions = InfoCard("Transactions", "0", "fa5s.receipt", "Loading...", True)
        cards_layout.addWidget(self.card_transactions, 0, 1)

        self.card_avg_sale = InfoCard(
            "Average Sale",
            format_currency(0),
            "fa5s.calculator",
            "Loading...",
            True,
        )
        cards_layout.addWidget(self.card_avg_sale, 0, 2)

        self.card_items_sold = InfoCard("Items Sold", "0", "fa5s.boxes", "Loading...", True)
        cards_layout.addWidget(self.card_items_sold, 0, 3)

        layout.addLayout(cards_layout)

        # --- Body: Recent Sales (left) + Right Column ---
        body_layout = QHBoxLayout()
        body_layout.setSpacing(20)

        # Left: Recent Transactions Panel
        recent_panel = QFrame()
        recent_panel.setObjectName("RecentSalesPanel")
        recent_layout = QVBoxLayout(recent_panel)
        recent_layout.setContentsMargins(16, 16, 16, 16)
        recent_layout.setSpacing(12)

        lbl_recent = QLabel("Recent Transactions")
        lbl_recent.setObjectName("SectionTitle")
        recent_layout.addWidget(lbl_recent)

        self.recent_table = QTableWidget()
        self.recent_table.setObjectName("RecentSalesTable")
        self.recent_table.setColumnCount(5)
        self.recent_table.setHorizontalHeaderLabels(["TIME", "DOC #", "CUSTOMER", "PAYMENT", "TOTAL"])
        self.recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.recent_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setShowGrid(False)
        recent_layout.addWidget(self.recent_table)

        body_layout.addWidget(recent_panel, 3)

        # Right Column: Top Products + Payment Breakdown
        right_column = QVBoxLayout()
        right_column.setSpacing(20)

        # Top Selling Today
        top_panel = QFrame()
        top_panel.setObjectName("TopProductsPanel")
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(16, 16, 16, 16)
        top_layout.setSpacing(12)

        lbl_top = QLabel("Top Selling Today")
        lbl_top.setObjectName("SectionTitle")
        top_layout.addWidget(lbl_top)

        self.top_table = QTableWidget()
        self.top_table.setObjectName("TopProductsTable")
        self.top_table.setColumnCount(3)
        self.top_table.setHorizontalHeaderLabels(["PRODUCT", "QTY", "REVENUE"])
        self.top_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.top_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.top_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.top_table.verticalHeader().setVisible(False)
        self.top_table.setShowGrid(False)
        top_layout.addWidget(self.top_table)

        right_column.addWidget(top_panel, 1)

        # Payment Breakdown
        pay_panel = QFrame()
        pay_panel.setObjectName("PaymentBreakdownPanel")
        pay_layout = QVBoxLayout(pay_panel)
        pay_layout.setContentsMargins(16, 16, 16, 16)
        pay_layout.setSpacing(12)

        lbl_pay = QLabel("Payment Methods")
        lbl_pay.setObjectName("SectionTitle")
        pay_layout.addWidget(lbl_pay)

        self.payment_table = QTableWidget()
        self.payment_table.setObjectName("PaymentBreakdownTable")
        self.payment_table.setColumnCount(2)
        self.payment_table.setHorizontalHeaderLabels(["METHOD", "TOTAL"])
        self.payment_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.payment_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.payment_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.payment_table.verticalHeader().setVisible(False)
        self.payment_table.setShowGrid(False)
        pay_layout.addWidget(self.payment_table)

        right_column.addWidget(pay_panel, 1)

        body_layout.addLayout(right_column, 2)

        layout.addLayout(body_layout, 1)

    def showEvent(self, event):
        """Auto-refresh data when the dashboard becomes visible."""
        super().showEvent(event)
        self.refresh_data()

    def refresh_data(self):
        from cbpos.core.services.dashboard_service import DashboardService

        try:
            kpis = DashboardService.get_kpis()
            yesterday = DashboardService.get_yesterday_kpis()

            # Update KPI cards
            self.card_sales.set_value(format_currency(kpis["total_sales"]))
            self._update_trend(self.card_sales, kpis["total_sales"], yesterday["total_sales"])

            self.card_transactions.set_value(str(kpis["txn_count"]))
            self._update_trend(self.card_transactions, kpis["txn_count"], yesterday["txn_count"])

            self.card_avg_sale.set_value(format_currency(kpis["avg_sale"]))
            self._update_trend(self.card_avg_sale, kpis["avg_sale"], yesterday["avg_sale"])

            self.card_items_sold.set_value(str(kpis["items_sold"]))
            self._update_trend(self.card_items_sold, kpis["items_sold"], yesterday["items_sold"])

            # Recent sales table
            recent = DashboardService.get_recent_sales(limit=10)
            self.recent_table.setRowCount(len(recent))
            for row, sale in enumerate(recent):
                self.recent_table.setItem(row, 0, QTableWidgetItem(sale["time"]))
                self.recent_table.setItem(row, 1, QTableWidgetItem(sale["doc_number"]))
                self.recent_table.setItem(row, 2, QTableWidgetItem(sale["customer"]))
                self.recent_table.setItem(row, 3, QTableWidgetItem(sale["payment"]))
                total_item = QTableWidgetItem(format_currency(sale["total"]))
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.recent_table.setItem(row, 4, total_item)

            # Top selling products
            top = DashboardService.get_top_selling_today(limit=5)
            self.top_table.setRowCount(len(top))
            for row, product in enumerate(top):
                self.top_table.setItem(row, 0, QTableWidgetItem(product["name"]))
                qty_item = QTableWidgetItem(str(product["qty"]))
                qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.top_table.setItem(row, 1, qty_item)
                rev_item = QTableWidgetItem(format_currency(product["revenue"]))
                rev_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.top_table.setItem(row, 2, rev_item)

            # Payment breakdown
            payments = DashboardService.get_payment_breakdown()
            self.payment_table.setRowCount(len(payments))
            for row, pay in enumerate(payments):
                self.payment_table.setItem(row, 0, QTableWidgetItem(pay["method"]))
                total_item = QTableWidgetItem(format_currency(pay["total"]))
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.payment_table.setItem(row, 1, total_item)

        except Exception:
            logger.exception("Failed to refresh dashboard data")

    @staticmethod
    def _update_trend(card: InfoCard, today_val, yesterday_val) -> None:
        """Compute % change between today and yesterday and update card trend."""
        today = Decimal(str(today_val))
        yesterday = Decimal(str(yesterday_val))

        if yesterday == 0:
            if today > 0:
                card.set_trend("New today", True)
            else:
                card.set_trend("No data", True)
            return

        change = ((today - yesterday) / yesterday) * Decimal("100")
        positive = change >= 0
        sign = "+" if positive else ""
        card.set_trend(f"{sign}{change:.0f}% vs yesterday", positive)  # noqa: E231
