from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import case, func, select

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.database import get_db_session
from cbpos.core.models import Category, Product, Sale, SaleItem, User
from cbpos.core.reports.base_report import CATEGORY_SALES, INT, MONEY, QTY, TEXT, BaseReport, report_columns
from cbpos.core.reports.sale_filters import date_bounds
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
        """Sum quantity sold and gross revenue (sale item subtotal) per category for completed sales and refunds.

        Voided sales are strictly excluded (#845).
        """
        date_range = filters.get("date_range", {})
        start_dt, end_dt = date_bounds(date_range)

        with get_db_session() as session:
            stmt = (
                select(
                    Category.name.label("category_name"),
                    func.sum(SaleItem.qty).label("qty_sold"),
                    func.sum(SaleItem.subtotal).label("gross_revenue"),
                )
                .join(Product, SaleItem.product_id == Product.id)
                .join(Category, Product.category_id == Category.id)
                .join(Sale, SaleItem.sale_id == Sale.id)
                .where(Sale.status == DocumentStatus.COMPLETED)
            )

            if start_dt:
                stmt = stmt.where(Sale.date >= start_dt)
            if end_dt:
                stmt = stmt.where(Sale.date < end_dt)

            results = session.execute(stmt.group_by(Category.name).order_by(func.sum(SaleItem.subtotal).desc())).all()

            data = []
            for row in results:
                data.append(
                    {
                        "Category": row.category_name,
                        "Qty Sold": row.qty_sold if row.qty_sold is not None else Decimal("0"),
                        "Gross Revenue": row.gross_revenue if row.gross_revenue is not None else Decimal("0.00"),
                    }
                )

            df = pd.DataFrame(data)
            if df.empty:
                df = pd.DataFrame(columns=["Category", "Qty Sold", "Gross Revenue"])
            return df


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
        """Sum transaction count and total sales per cashier for completed sales and refunds.

        Voided sales are strictly excluded (#845).
        Refund documents reduce total sales but do not increment transaction count.
        """
        date_range = filters.get("date_range", {})
        start_dt, end_dt = date_bounds(date_range)

        with get_db_session() as session:
            stmt = (
                select(
                    User.username.label("cashier_name"),
                    func.count(case((Sale.refund_of_sale_id.is_(None), Sale.id))).label("txn_count"),
                    func.sum(Sale.total_amount).label("total_sales"),
                )
                .join(User, Sale.user_id == User.id)
                .where(Sale.status == DocumentStatus.COMPLETED)
            )

            if start_dt:
                stmt = stmt.where(Sale.date >= start_dt)
            if end_dt:
                stmt = stmt.where(Sale.date < end_dt)

            results = session.execute(stmt.group_by(User.username).order_by(func.sum(Sale.total_amount).desc())).all()

            data = []
            for row in results:
                data.append(
                    {
                        "Cashier Name": row.cashier_name,
                        "Transaction Count": int(row.txn_count or 0),
                        "Total Sales": row.total_sales if row.total_sales is not None else Decimal("0.00"),
                    }
                )

            df = pd.DataFrame(data)
            if df.empty:
                df = pd.DataFrame(columns=["Cashier Name", "Transaction Count", "Total Sales"])
            return df
