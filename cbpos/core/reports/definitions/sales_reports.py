from typing import Any

import pandas as pd
from sqlalchemy import func

from cbpos.core.database import get_db_session
from cbpos.core.models import Category, Product, Sale, SaleItem, User
from cbpos.core.reports.base_report import CATEGORY_SALES, INT, MONEY, QTY, TEXT, BaseReport, report_columns
from cbpos.i18n import _t


class SalesByCategoryReport(BaseReport):
    """Quantity sold and gross revenue per product category within a date range."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "sales_by_category"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.sales_by_category")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_SALES

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range filter only."""
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so quantities and money right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Category": TEXT,
                    "Qty Sold": QTY,
                    "Gross Revenue": MONEY,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Sum quantity sold and gross revenue (sale item subtotal) per category."""
        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            # Join SaleItem -> Product -> Category
            # Filter by Sale Date
            query = (
                session.query(
                    Category.name.label("category_name"),
                    func.sum(SaleItem.qty).label("qty_sold"),
                    func.sum(SaleItem.subtotal).label("gross_revenue"),
                )
                .join(Product, SaleItem.product_id == Product.id)
                .join(Category, Product.category_id == Category.id)
                .join(Sale, SaleItem.sale_id == Sale.id)
            )

            if start_date:
                query = query.filter(func.date(Sale.date) >= start_date)
            if end_date:
                query = query.filter(func.date(Sale.date) <= end_date)

            results = query.group_by(Category.name).all()

            data = []
            for row in results:
                data.append(
                    {
                        "Category": row.category_name,
                        "Qty Sold": float(row.qty_sold or 0),
                        "Gross Revenue": float(row.gross_revenue or 0),
                    }
                )

            return pd.DataFrame(data)


class CashierPerformanceReport(BaseReport):
    """Transaction count and total sales per cashier within a date range."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "cashier_performance"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.cashier_performance")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_SALES

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range filter only."""
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so counts and money right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Cashier Name": TEXT,
                    "Transaction Count": INT,
                    "Total Sales": MONEY,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Sum transaction count and total sales per cashier (user)."""
        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            query = session.query(
                User.username.label("cashier_name"),
                func.count(Sale.id).label("txn_count"),
                func.sum(Sale.total_amount).label("total_sales"),
            ).join(User, Sale.user_id == User.id)

            if start_date:
                query = query.filter(func.date(Sale.date) >= start_date)
            if end_date:
                query = query.filter(func.date(Sale.date) <= end_date)

            results = query.group_by(User.username).all()

            data = []
            for row in results:
                data.append(
                    {
                        "Cashier Name": row.cashier_name,
                        "Transaction Count": int(row.txn_count or 0),
                        "Total Sales": float(row.total_sales or 0),
                    }
                )

            return pd.DataFrame(data)
