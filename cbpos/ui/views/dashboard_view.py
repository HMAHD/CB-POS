from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer
from cbpos.ui.widgets.custom_widgets import InfoCard
from cbpos.ui.resources.icons import Icons
from cbpos.core.database import Database
from cbpos.core.models import Sale
from sqlalchemy import func
from datetime import datetime


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.refresh_stats()

        # Auto-refresh every 30 seconds
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_stats)
        self.timer.start(30000)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Header
        header = QLabel("DASHBOARD")
        header.setStyleSheet("font-size: 32px; font-weight: bold; color: #39FF14; ")
        layout.addWidget(header)

        # Cards Grid
        self.grid = QGridLayout()
        self.grid.setSpacing(20)

        self.card_sales = InfoCard("Total Sales", "Rs. 0.00", Icons.SALES, "#39FF14")
        self.card_trans = InfoCard("Transactions", "0", Icons.REPORTS, "#00BCEB")
        self.card_customers = InfoCard("New Customers", "0", Icons.CUSTOMERS, "#FFDC00")
        self.card_voids = InfoCard("Voided Bills", "0", Icons.VOID, "#FF4136")

        self.grid.addWidget(self.card_sales, 0, 0)
        self.grid.addWidget(self.card_trans, 0, 1)
        self.grid.addWidget(self.card_customers, 0, 2)
        self.grid.addWidget(self.card_voids, 0, 3)

        layout.addLayout(self.grid)
        layout.addStretch()

    def refresh_stats(self):
        """Fetch stats from DB."""
        db = Database()
        with db.get_session() as session:
            # Today's Sales
            today = datetime.now().date()

            # Total Revenue
            total_revenue = (
                session.query(func.sum(Sale.total_amount))
                .filter(func.date(Sale.date) == today, Sale.status != "VOID")
                .scalar()
                or 0
            )

            # Transaction Count
            trans_count = (
                session.query(func.count(Sale.id))
                .filter(func.date(Sale.date) == today, Sale.status != "VOID")
                .scalar()
                or 0
            )

            # Void Count
            void_count = (
                session.query(func.count(Sale.id))
                .filter(func.date(Sale.date) == today, Sale.status == "VOID")
                .scalar()
                or 0
            )

            # Update UI
            revenue_formatted = "Rs. {:,.2f}".format(total_revenue)
            self.card_sales.set_value(revenue_formatted)
            self.card_trans.set_value(str(trans_count))
            self.card_voids.set_value(str(void_count))
            # Customer count requires Customer model query (skipped)
