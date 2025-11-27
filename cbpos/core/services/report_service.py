from datetime import date, datetime
from typing import Dict, List, Any
from sqlalchemy import select, func, desc, extract
from cbpos.core.database import Database
from cbpos.core.models import Sale, SaleItem, SalePayment, Product


class ReportService:
    def __init__(self):
        self.db = Database()

    def get_daily_sales(self, report_date: date) -> Dict[str, Any]:
        with self.db.get_session() as session:
            # Filter by date
            start_dt = datetime.combine(report_date, datetime.min.time())
            end_dt = datetime.combine(report_date, datetime.max.time())

            # Total Sales
            total_sales = (
                session.scalar(
                    select(func.sum(Sale.total_amount)).where(
                        Sale.date >= start_dt, Sale.date <= end_dt
                    )
                )
                or 0
            )

            # Total Tax
            total_tax = (
                session.scalar(
                    select(func.sum(Sale.tax_vat + Sale.tax_sscl)).where(
                        Sale.date >= start_dt, Sale.date <= end_dt
                    )
                )
                or 0
            )

            # Payment Breakdown
            payment_breakdown = session.execute(
                select(SalePayment.payment_method, func.sum(SalePayment.amount))
                .join(Sale)
                .where(Sale.date >= start_dt, Sale.date <= end_dt)
                .group_by(SalePayment.payment_method)
            ).all()

            return {
                "date": report_date,
                "total_sales": total_sales,
                "total_tax": total_tax,
                "payment_breakdown": {
                    method: amount for method, amount in payment_breakdown
                },
            }

    def get_top_products(self, limit: int = 10) -> List[Dict[str, Any]]:
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

    def get_hourly_sales(self, report_date: date) -> List[Dict[str, Any]]:
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
