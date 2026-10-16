from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import func, select

from cbpos.core.database import Database
from cbpos.core.models import Sale
from cbpos.core.reports.base_report import CATEGORY_SALES, DATE, INT, MONEY, BaseReport, report_columns
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
        return CATEGORY_SALES

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

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so counts and money right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Date": DATE,
                    "Transactions": INT,
                    "Total Sales": MONEY,
                }
            )
        }

    def get_summary(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Compute KPI summary cards for daily sales: Total Sales, Invoices, Avg Ticket (#543)."""
        from cbpos.core.services.config_service import ConfigService
        from cbpos.ui.resources.icons import Icons

        currency = ConfigService.get("currency_symbol") or "Rs."

        if df is None or df.empty:
            return [
                {
                    "key": "total_sales",
                    "title": _t("reports.summary_total_sales"),
                    "value": f"{currency} 0.00",
                    "icon": Icons.SALES,
                    "color": "#10B981",
                },
                {
                    "key": "invoices",
                    "title": _t("reports.summary_invoices"),
                    "value": "0",
                    "icon": Icons.REPORTS,
                    "color": "#00BCEB",
                },
                {
                    "key": "avg_ticket",
                    "title": _t("reports.summary_avg_ticket"),
                    "value": f"{currency} 0.00",
                    "icon": Icons.PAY,
                    "color": "#F59E0B",
                },
            ]

        # Total Sales
        total_sales = 0.0
        if "Total Sales" in df.columns:
            total_sales = float(pd.to_numeric(df["Total Sales"], errors="coerce").fillna(0.0).sum())

        # Invoices / Transactions count
        invoices = 0
        if "Transactions" in df.columns:
            invoices = int(pd.to_numeric(df["Transactions"], errors="coerce").fillna(0).sum())
        elif "Total Invoices" in df.columns:
            invoices = int(pd.to_numeric(df["Total Invoices"], errors="coerce").fillna(0).sum())
        else:
            invoices = len(df)

        avg_ticket = (total_sales / invoices) if invoices > 0 else 0.0

        return [
            {
                "key": "total_sales",
                "title": _t("reports.summary_total_sales"),
                "value": f"{currency} {total_sales:,.2f}",
                "icon": Icons.SALES,
                "color": "#10B981",
            },
            {
                "key": "invoices",
                "title": _t("reports.summary_invoices"),
                "value": f"{invoices:,}",
                "icon": Icons.REPORTS,
                "color": "#00BCEB",
            },
            {
                "key": "avg_ticket",
                "title": _t("reports.summary_avg_ticket"),
                "value": f"{currency} {avg_ticket:,.2f}",
                "icon": Icons.PAY,
                "color": "#F59E0B",
            },
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
