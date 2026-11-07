from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd
from sqlalchemy import desc, extract, func, select

from cbpos.core.database import Database
from cbpos.core.models import Product, Sale, SaleItem, SalePayment

if TYPE_CHECKING:
    from cbpos.core.reports.base_report import BaseReport


class ReportService:
    """Ad-hoc reporting queries: daily sales, top products, hourly trends, and stock valuation."""

    def __init__(self):
        """Bind this service instance to the database singleton."""
        self.db = Database()

    def get_daily_sales(self, report_date: date) -> dict[str, Any]:
        """Return total sales, total VAT+SSCL, and a payment-method breakdown for one calendar day."""
        with self.db.get_session() as session:
            # Filter by date
            start_dt = datetime.combine(report_date, datetime.min.time())
            end_dt = datetime.combine(report_date, datetime.max.time())

            # Total Sales
            total_sales = (
                session.scalar(select(func.sum(Sale.total_amount)).where(Sale.date >= start_dt, Sale.date <= end_dt))
                or 0
            )

            # Total Tax
            total_tax = (
                session.scalar(
                    select(func.sum(Sale.tax_vat + Sale.tax_sscl)).where(Sale.date >= start_dt, Sale.date <= end_dt)
                )
                or 0
            )

            # Payment Breakdown
            # TODO(#844): use method_kind
            payment_breakdown = session.execute(
                select(SalePayment.payment_method, func.sum(SalePayment.amount))  # TODO(#844): use method_kind
                .join(Sale)
                .where(Sale.date >= start_dt, Sale.date <= end_dt)
                .group_by(SalePayment.payment_method)
            ).all()

            return {
                "date": report_date,
                "total_sales": total_sales,
                "total_tax": total_tax,
                "payment_breakdown": dict(payment_breakdown),
            }

    def get_top_products(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the top-selling products across all time, ranked by quantity sold."""
        with self.db.get_session() as session:
            # Top selling products by quantity
            results = session.execute(
                select(Product.name_en, func.sum(SaleItem.qty).label("total_qty"))
                .join(SaleItem)
                .group_by(Product.id)
                .order_by(desc("total_qty"))
                .limit(limit)
            ).all()

            return [{"name": name, "qty": qty} for name, qty in results]

    def get_hourly_sales(self, report_date: date) -> list[dict[str, Any]]:
        """Return sales totals for every hour (0-23) of one calendar day, zero-filled for gaps."""
        with self.db.get_session() as session:
            start_dt = datetime.combine(report_date, datetime.min.time())
            end_dt = datetime.combine(report_date, datetime.max.time())

            # Extract hour from timestamp (SQLite specific syntax might be needed depending on dialect,
            # but SQLAlchemy extract usually handles it)
            results = session.execute(
                select(
                    extract("hour", Sale.date).label("hour"),
                    func.sum(Sale.total_amount),
                )
                .where(Sale.date >= start_dt, Sale.date <= end_dt)
                .group_by("hour")
                .order_by("hour")
            ).all()

            # Fill in missing hours
            sales_by_hour = {int(r[0]): r[1] for r in results}
            final_data = []
            for h in range(24):  # 0 to 23
                final_data.append({"hour": h, "sales": sales_by_hour.get(h, 0)})

            return final_data

    def get_stock_valuation(self) -> dict[str, Any]:
        """Calculate stock valuation metrics.

        Returns::

            {
                'total_cost_value': Decimal,
                'total_retail_value': Decimal,
                'potential_profit': Decimal,
                'category_breakdown': List[dict]
            }
        """
        with self.db.get_session() as session:
            from decimal import Decimal

            from cbpos.core.models import Category

            # Calculate total stock value
            total_cost = session.scalar(
                select(func.sum(Product.cost * Product.stock_qty)).where(Product.is_active == True)  # noqa: E712
            ) or Decimal("0.00")

            total_retail = session.scalar(
                select(func.sum(Product.price * Product.stock_qty)).where(Product.is_active == True)  # noqa: E712
            ) or Decimal("0.00")

            potential_profit = total_retail - total_cost

            # Category breakdown
            category_results = session.execute(
                select(
                    Category.name,
                    func.sum(Product.cost * Product.stock_qty).label("cost_value"),
                    func.sum(Product.price * Product.stock_qty).label("retail_value"),
                    func.count(Product.id).label("product_count"),
                )
                .join(Product, Product.category_id == Category.id)
                .where(Product.is_active == True)  # noqa: E712
                .group_by(Category.id)
                .order_by(desc("retail_value"))
            ).all()

            category_breakdown = [
                {
                    "category": name,
                    "cost_value": cost_val or Decimal("0.00"),
                    "retail_value": retail_val or Decimal("0.00"),
                    "product_count": count,
                    "profit": (retail_val or Decimal("0.00")) - (cost_val or Decimal("0.00")),
                }
                for name, cost_val, retail_val, count in category_results
            ]

            return {
                "total_cost_value": total_cost,
                "total_retail_value": total_retail,
                "potential_profit": potential_profit,
                "category_breakdown": category_breakdown,
            }

    @staticmethod
    def available_reports(user: Any = None) -> list["BaseReport"]:
        """Return all reports that the given user has permission to view.

        If a user is provided and has a role, only reports whose required_permission
        is granted to that role are returned. If user is None or has no role,
        all registered reports are returned.
        """
        from cbpos.core.reports.registry import ReportRegistry
        from cbpos.core.services.permission_service import PermissionService

        all_reports = list(ReportRegistry()._all_reports.values())
        if user is None or getattr(user, "role_id", None) is None:
            return all_reports

        return [r for r in all_reports if PermissionService.user_has_permission(user, r.required_permission)]

    @staticmethod
    def run(report_id: str, params: dict[str, Any], user: Any = None) -> pd.DataFrame:
        """Run a registered report by ID after verifying user permissions.

        Scheduled auto-email reports (scheduler_service.py) run as the system
        (user=None). When an authenticated user is provided, required_permission is
        enforced before generating data.
        """
        from cbpos.core.reports.registry import ReportRegistry
        from cbpos.core.services.permission_service import PermissionService

        report = ReportRegistry().get_report_by_id(report_id)
        if not report:
            raise ValueError(f"Unknown report: {report_id}")

        if user is not None and getattr(user, "role_id", None) is not None:
            if not PermissionService.user_has_permission(user, report.required_permission):
                raise PermissionError(f"Permission denied: {report.required_permission} required")

        return report.generate(params)
