from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import func, select

from cbpos.core.database import Database
from cbpos.core.models import Sale
from cbpos.core.reports.base_report import BaseReport
from cbpos.i18n import _t


class DailySalesSummaryReport(BaseReport):
    """Transaction count and total sales revenue grouped by day."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "daily_sales_summary"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.daily_sales_summary")

    @property
    def category(self) -> str:
        """Report category."""
        return _t("reports.category_sales")

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range filter, defaulting to today."""
        return [
            {
                "name": "date_range",
                "type": "date_range",
                "label": "Date Range",
                "default_start": date.today(),
                "default_end": date.today(),
            }
        ]

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Group sales by calendar date within the range, summing count and total.

        Returns an empty DataFrame if no date range is provided.
        """
        start_date = filters.get("date_range", {}).get("start")
        end_date = filters.get("date_range", {}).get("end")

        if not start_date or not end_date:
            return pd.DataFrame()

        with Database().get_session() as session:
            # Query: Group by Date and Sum Total Amount
            # Note: SQLite stores dates as strings usually, but SQLAlchemy handles
            # it if typed correctly.
            # Assuming Sale.date is a Date or DateTime object.

            # If Sale.date is DateTime, we might need to cast to Date for grouping.
            # For simplicity, assuming we filter by range and just list sales or
            # group by day.
            # The prompt says: "Group by Date -> Sum Total".

            stmt = (
                select(
                    func.date(Sale.date).label("sale_date"),
                    func.count(Sale.id).label("transaction_count"),
                    func.sum(Sale.total_amount).label("total_sales"),
                )
                .filter(func.date(Sale.date) >= start_date)
                .filter(func.date(Sale.date) <= end_date)
                .group_by(func.date(Sale.date))
                .order_by(func.date(Sale.date))
            )

            results = session.execute(stmt).all()

            data = []
            for row in results:
                data.append(
                    {
                        "Date": row.sale_date,
                        "Transactions": row.transaction_count,
                        "Total Sales": float(row.total_sales) if row.total_sales else 0.0,
                    }
                )

            df = pd.DataFrame(data)

            # Ensure columns exist even if empty
            if df.empty:
                df = pd.DataFrame(columns=["Date", "Transactions", "Total Sales"])

            return df
