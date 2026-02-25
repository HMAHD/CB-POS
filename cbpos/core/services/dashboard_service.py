from decimal import Decimal
from sqlalchemy import func, extract
from datetime import date
from cbpos.core.database import Database
from cbpos.core.models import Sale, Product, Shift
from cbpos.core.constants.status import ShiftStatus


class DashboardService:
    @staticmethod
    def get_kpis() -> dict:
        """
        Fetch Key Performance Indicators for the Dashboard.
        """
        db = Database()
        with db.get_session() as session:
            today = date.today()

            # 1. Total Sales (Today)
            total_sales = session.query(func.sum(Sale.total_amount)).filter(func.date(Sale.date) == today).scalar() or 0

            # 2. Transaction Count (Today)
            txn_count = session.query(func.count(Sale.id)).filter(func.date(Sale.date) == today).scalar() or 0

            # 3. Low Stock Count
            low_stock_count = (
                session.query(func.count(Product.id))
                .filter(Product.is_active)
                .filter(Product.stock_qty <= Product.reorder_point)
                .scalar()
                or 0
            )

            # 4. Active Staff (Open Shifts)
            active_staff = session.query(func.count(Shift.id)).filter(Shift.status == ShiftStatus.OPEN).scalar() or 0

            return {
                "total_sales": total_sales,
                "txn_count": txn_count,
                "low_stock_count": low_stock_count,
                "active_staff": active_staff,
            }

    @staticmethod
    def get_hourly_sales() -> list:
        """
        Get sales count grouped by hour for today.
        Returns a fixed-length list of 24 integers (0-23).
        """
        db = Database()
        with db.get_session() as session:
            today = date.today()

            # Query sales grouped by hour
            # SQLite extract('hour', ...) might behave differently than Postgres
            # For SQLite, we might need strftime('%H', ...)
            # But SQLAlchemy 'extract' usually abstracts this.
            # Let's try standard extract first, if it fails we fallback to func.strftime

            try:
                hourly_data = (
                    session.query(
                        extract("hour", Sale.date).label("hour"),
                        func.sum(Sale.total_amount).label("total"),
                    )
                    .filter(func.date(Sale.date) == today)
                    .group_by("hour")
                    .all()
                )
            except Exception:
                # Fallback for SQLite if extract doesn't work as expected
                hourly_data = (
                    session.query(
                        func.strftime("%H", Sale.date).label("hour"),
                        func.sum(Sale.total_amount).label("total"),
                    )
                    .filter(func.date(Sale.date) == today)
                    .group_by("hour")
                    .all()
                )

            # Initialize 24-hour list with 0
            sales_by_hour = [0] * 24

            for hour, total in hourly_data:
                if hour is not None:
                    h_idx = int(hour)
                    if 0 <= h_idx < 24:
                        sales_by_hour[h_idx] = Decimal(str(total)) if total else Decimal("0")

            return sales_by_hour
