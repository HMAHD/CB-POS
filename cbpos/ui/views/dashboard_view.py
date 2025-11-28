from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
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

        # 1. Top Row: Info Cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)

        # Card 1: Revenue
        self.card_revenue = InfoCard(
            "Total Revenue", "Rs. 45,200", "fa5s.rupee-sign", "+12% vs yesterday", True
        )
        cards_layout.addWidget(self.card_revenue)

        # Card 2: Transactions
        self.card_transactions = InfoCard(
            "Transactions", "128", "fa5s.receipt", "+5% vs yesterday", True
        )
        cards_layout.addWidget(self.card_transactions)

        # Card 3: Low Stock
        self.card_low_stock = InfoCard(
            "Low Stock Items",
            "3",
            "fa5s.exclamation-triangle",
            "Needs Attention",
            False,
        )
        cards_layout.addWidget(self.card_low_stock)

        # Card 4: Active Staff
        self.card_staff = InfoCard(
            "Active Staff", "4", "fa5s.users", "All systems normal", True
        )
        cards_layout.addWidget(self.card_staff)

        layout.addLayout(cards_layout)

        # 2. Center Section: Chart Placeholder
        chart_frame = QFrame()
        chart_frame.setStyleSheet(
            "background-color: #001F3F; border: 1px solid #003366; border-radius: 8px;"
        )
        chart_layout = QVBoxLayout(chart_frame)

        lbl_chart = QLabel("Sales Overview (Chart Placeholder)")
        lbl_chart.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_chart.setStyleSheet("color: #AAAAAA; font-size: 16px;")
        chart_layout.addWidget(lbl_chart)

        layout.addWidget(chart_frame, stretch=1)

        # 3. Bottom Section: Recent Activity
        lbl_activity = QLabel("Recent System Activity")
        lbl_activity.setStyleSheet(
            "color: #FFFFFF; font-size: 14px; font-weight: bold; margin-top: 10px;"
        )
        layout.addWidget(lbl_activity)

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["Time", "User", "Action"])
        self.log_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_table.setFixedHeight(200)
        self.log_table.setStyleSheet(
            """
            QTableWidget {
                background-color: #001F3F;
                border: 1px solid #003366;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #003366;
                color: white;
                border: none;
                padding: 5px;
            }
        """
        )

        layout.addWidget(self.log_table)

        # Load initial data
        self.refresh_data()

    def refresh_data(self):
        # Refresh logs
        logs = UserService.get_recent_activity(limit=10)
        self.log_table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            self.log_table.setItem(
                row, 0, QTableWidgetItem(log.timestamp.strftime("%H:%M:%S"))
            )
            self.log_table.setItem(
                row, 1, QTableWidgetItem(log.user.username if log.user else "Unknown")
            )
            self.log_table.setItem(
                row, 2, QTableWidgetItem(f"{log.event_type}: {log.details}")
            )
