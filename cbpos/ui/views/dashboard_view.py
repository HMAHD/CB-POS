from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QGridLayout,
)
from PyQt6.QtCore import Qt
from cbpos.ui.widgets.info_card import InfoCard
from cbpos.core.services.user_service import UserService


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # 1. Top Row: Info Cards (Grid Layout)
        cards_layout = QGridLayout()
        cards_layout.setSpacing(20)

        # Card 1: Revenue
        self.card_revenue = InfoCard("Total Revenue", "Rs. 45,200", "fa5s.rupee-sign", "+12% vs yesterday", True)
        cards_layout.addWidget(self.card_revenue, 0, 0)

        # Card 2: Transactions
        self.card_transactions = InfoCard("Transactions", "128", "fa5s.receipt", "+5% vs yesterday", True)
        cards_layout.addWidget(self.card_transactions, 0, 1)

        # Card 3: Low Stock
        self.card_low_stock = InfoCard(
            "Low Stock Items",
            "3",
            "fa5s.exclamation-triangle",
            "Needs Attention",
            False,
        )
        cards_layout.addWidget(self.card_low_stock, 0, 2)

        # Card 4: Active Staff
        self.card_staff = InfoCard("Active Staff", "4", "fa5s.users", "All systems normal", True)
        cards_layout.addWidget(self.card_staff, 0, 3)

        layout.addLayout(cards_layout)

        # 2. Center Section: Chart Placeholder
        chart_frame = QFrame()
        chart_frame.setObjectName("ChartPlaceholder")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(40, 40, 40, 40)

        lbl_chart = QLabel("Sales Overview (Chart Placeholder)")
        lbl_chart.setObjectName("ChartPlaceholderText")
        lbl_chart.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chart_layout.addWidget(lbl_chart)

        layout.addWidget(chart_frame, stretch=1)

        # 3. Bottom Section: Recent Activity
        lbl_activity = QLabel("Recent System Activity")
        lbl_activity.setObjectName("SectionTitle")
        layout.addWidget(lbl_activity)

        self.log_table = QTableWidget()
        self.log_table.setObjectName("ActivityTable")
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["TIME", "USER", "ACTION"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setShowGrid(False)
        self.log_table.setFixedHeight(250)

        layout.addWidget(self.log_table)

        # Load initial data
        self.refresh_data()

    def refresh_data(self):
        from cbpos.core.services.dashboard_service import DashboardService
        from cbpos.core.utils.formatters import format_currency

        # Fetch KPIs
        kpis = DashboardService.get_kpis()

        # Update Cards
        self.card_revenue.set_value(format_currency(kpis["total_sales"]))
        self.card_transactions.set_value(str(kpis["txn_count"]))
        self.card_low_stock.set_value(str(kpis["low_stock_count"]))
        self.card_staff.set_value(str(kpis["active_staff"]))

        # Fetch Hourly Sales (For Chart)
        hourly_sales = DashboardService.get_hourly_sales()
        print(f"[DASHBOARD] Hourly Sales: {hourly_sales}")

        # Refresh logs
        logs = UserService.get_recent_activity(limit=10)
        self.log_table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            self.log_table.setItem(row, 0, QTableWidgetItem(log.timestamp.strftime("%H:%M:%S")))
            self.log_table.setItem(row, 1, QTableWidgetItem(log.user.username if log.user else "Unknown"))
            self.log_table.setItem(row, 2, QTableWidgetItem(f"{log.event_type}: {log.details}"))
