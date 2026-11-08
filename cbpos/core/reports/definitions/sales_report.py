from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import case, func, select

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.database import Database
from cbpos.core.models import Sale
from cbpos.core.reports.base_report import CATEGORY_SALES, DATE, INT, MONEY, BaseReport, report_columns
from cbpos.core.reports.sale_filters import date_bounds
from cbpos.core.services.config_service import ConfigService
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
        """Calculate KPI summary cards for daily sales: Total Sales, Invoices, Avg Ticket (#543)."""
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
        total_sales = Decimal("0.00")
        if "Total Sales" in df.columns:
            for val in df["Total Sales"]:
                if isinstance(val, Decimal):
                    total_sales += val
                elif val is not None and not pd.isna(val):
                    total_sales += Decimal(str(val))

        # Invoices / Transactions count
        invoices = 0
        if "Transactions" in df.columns:
            invoices = int(pd.to_numeric(df["Transactions"], errors="coerce").fillna(0).sum())
        elif "Total Invoices" in df.columns:
            invoices = int(pd.to_numeric(df["Total Invoices"], errors="coerce").fillna(0).sum())
        else:
            invoices = len(df)

        avg_ticket = (total_sales / Decimal(invoices)) if invoices > 0 else Decimal("0.00")

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
        """Group completed sales and refunds by calendar date within the range, summing count and total.

        Voided transactions are strictly excluded (#845).
        Refund documents reduce total sales but do not increment transaction count.
        """
        start_date = filters.get("date_range", {}).get("start")
        end_date = filters.get("date_range", {}).get("end")

        if not start_date or not end_date:
            return pd.DataFrame(columns=["Date", "Transactions", "Total Sales"])

        start_dt, end_dt = date_bounds(filters.get("date_range", {}))

        with Database().get_session() as session:
            stmt = select(
                func.date(Sale.date).label("sale_date"),
                func.count(case((Sale.refund_of_sale_id.is_(None), Sale.id))).label("transaction_count"),
                func.sum(
                    case(
                        (Sale.refund_of_sale_id.is_not(None), -func.abs(Sale.total_amount)),
                        else_=Sale.total_amount,
                    )
                ).label("total_sales"),
            ).where(Sale.status == DocumentStatus.COMPLETED)

            if start_dt:
                stmt = stmt.where(Sale.date >= start_dt)
            if end_dt:
                stmt = stmt.where(Sale.date < end_dt)

            stmt = stmt.group_by(func.date(Sale.date)).order_by(func.date(Sale.date))

            results = session.execute(stmt).all()

            data = []
            for row in results:
                data.append(
                    {
                        "Date": row.sale_date,
                        "Transactions": int(row.transaction_count or 0),
                        "Total Sales": row.total_sales if row.total_sales is not None else Decimal("0.00"),
                    }
                )

            df = pd.DataFrame(data)
            if df.empty:
                df = pd.DataFrame(columns=["Date", "Transactions", "Total Sales"])

            return df
