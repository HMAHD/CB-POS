"""Dashboard data service for KPIs, charts, and periodic reports."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, Integer
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import (
    Sale,
    Product,
    Shift,
    SaleItem,
    SalePayment,
    Category,
    Customer,
)
from cbpos.core.constants.status import ShiftStatus

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


class DashboardService:
    # ------------------------------------------------------------------
    # Today / Yesterday KPIs (kept for backward compatibility)
    # ------------------------------------------------------------------

    @staticmethod
    def get_kpis() -> dict:
        """Today's KPIs: total_sales, txn_count, items_sold, avg_sale,
        low_stock_count, active_staff."""
        db = Database()
        with db.get_session() as session:
            today = date.today()

            total_sales = session.query(func.sum(Sale.total_amount)).filter(
                func.date(Sale.date) == today
            ).scalar() or Decimal("0")

            txn_count = session.query(func.count(Sale.id)).filter(func.date(Sale.date) == today).scalar() or 0

            items_sold = session.query(func.sum(SaleItem.qty)).join(Sale, SaleItem.sale_id == Sale.id).filter(
                func.date(Sale.date) == today
            ).scalar() or Decimal("0")

            avg_sale = Decimal(str(total_sales)) / Decimal(str(txn_count)) if txn_count > 0 else Decimal("0")

            low_stock_count = (
                session.query(func.count(Product.id))
                .filter(Product.is_active)
                .filter(Product.stock_qty <= Product.reorder_point)
                .scalar()
                or 0
            )

            active_staff = session.query(func.count(Shift.id)).filter(Shift.status == ShiftStatus.OPEN).scalar() or 0

            return {
                "total_sales": Decimal(str(total_sales)),
                "txn_count": txn_count,
                "items_sold": int(items_sold),
                "avg_sale": avg_sale,
                "low_stock_count": low_stock_count,
                "active_staff": active_staff,
            }

    @staticmethod
    def get_yesterday_kpis() -> dict:
        """Yesterday's KPIs for trend calculation."""
        db = Database()
        with db.get_session() as session:
            yesterday = date.today() - timedelta(days=1)

            total_sales = session.query(func.sum(Sale.total_amount)).filter(
                func.date(Sale.date) == yesterday
            ).scalar() or Decimal("0")

            txn_count = session.query(func.count(Sale.id)).filter(func.date(Sale.date) == yesterday).scalar() or 0

            items_sold = session.query(func.sum(SaleItem.qty)).join(Sale, SaleItem.sale_id == Sale.id).filter(
                func.date(Sale.date) == yesterday
            ).scalar() or Decimal("0")

            avg_sale = Decimal(str(total_sales)) / Decimal(str(txn_count)) if txn_count > 0 else Decimal("0")

            return {
                "total_sales": Decimal(str(total_sales)),
                "txn_count": txn_count,
                "items_sold": int(items_sold),
                "avg_sale": avg_sale,
            }

    # ------------------------------------------------------------------
    # Yearly / Monthly
    # ------------------------------------------------------------------

    @staticmethod
    def get_monthly_sales(year: int) -> list[dict]:
        """Monthly sales totals for a given year (12 entries)."""
        db = Database()
        with db.get_session() as session:
            rows = (
                session.query(
                    func.cast(func.strftime("%m", Sale.date), Integer).label("month"),
                    func.sum(Sale.total_amount).label("total"),
                )
                .filter(func.strftime("%Y", Sale.date) == str(year))
                .group_by("month")
                .all()
            )

            month_map = {r.month: Decimal(str(r.total or 0)) for r in rows}
            return [
                {
                    "month": i,
                    "label": MONTH_NAMES[i - 1][:3],
                    "total": month_map.get(i, Decimal("0")),
                }
                for i in range(1, 13)
            ]

    @staticmethod
    def get_yearly_summary(year: int) -> dict:
        """Yearly total and top performing month."""
        monthly = DashboardService.get_monthly_sales(year)
        yearly_total = sum(m["total"] for m in monthly)

        top = max(monthly, key=lambda m: m["total"])
        return {
            "total": yearly_total,
            "top_month_name": MONTH_NAMES[top["month"] - 1],
            "top_month_total": top["total"],
        }

    # ------------------------------------------------------------------
    # Periodic (date-range) queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_period_top_products(start_date: date, end_date: date, limit: int = 5) -> list[dict]:
        """Top products by revenue within a date range."""
        db = Database()
        with db.get_session() as session:
            rows = (
                session.query(
                    Product.name_en,
                    func.sum(SaleItem.subtotal).label("total"),
                )
                .join(SaleItem, SaleItem.product_id == Product.id)
                .join(Sale, SaleItem.sale_id == Sale.id)
                .filter(
                    func.date(Sale.date) >= start_date,
                    func.date(Sale.date) <= end_date,
                )
                .group_by(Product.id)
                .order_by(func.sum(SaleItem.subtotal).desc())
                .limit(limit)
                .all()
            )

            return [{"name": r[0], "total": Decimal(str(r[1] or 0))} for r in rows]

    @staticmethod
    def get_hourly_sales(start_date: date, end_date: date) -> list[dict]:
        """Hourly sales distribution within a date range (hours 6-22)."""
        db = Database()
        with db.get_session() as session:
            rows = (
                session.query(
                    func.cast(func.strftime("%H", Sale.date), Integer).label("hour"),
                    func.sum(Sale.total_amount).label("total"),
                )
                .filter(
                    func.date(Sale.date) >= start_date,
                    func.date(Sale.date) <= end_date,
                )
                .group_by("hour")
                .all()
            )

            hour_map = {r.hour: Decimal(str(r.total or 0)) for r in rows}

            # Return business hours 6AM-10PM, filling gaps with zero
            results = []
            for h in range(6, 23):
                display_h = h if h <= 12 else h - 12
                suffix = "AM" if h < 12 else "PM"
                results.append(
                    {
                        "hour": h,
                        "label": str(display_h) + suffix,
                        "total": hour_map.get(h, Decimal("0")),
                    }
                )
            return results

    @staticmethod
    def get_period_stats(start_date: date, end_date: date) -> dict:
        """Quick stats for a date range: avg_order, items_sold,
        unique_customers, txn_count."""
        db = Database()
        with db.get_session() as session:
            total_sales = session.query(func.sum(Sale.total_amount)).filter(
                func.date(Sale.date) >= start_date,
                func.date(Sale.date) <= end_date,
            ).scalar() or Decimal("0")

            txn_count = (
                session.query(func.count(Sale.id))
                .filter(
                    func.date(Sale.date) >= start_date,
                    func.date(Sale.date) <= end_date,
                )
                .scalar()
                or 0
            )

            items_sold = session.query(func.sum(SaleItem.qty)).join(Sale, SaleItem.sale_id == Sale.id).filter(
                func.date(Sale.date) >= start_date,
                func.date(Sale.date) <= end_date,
            ).scalar() or Decimal("0")

            unique_customers = (
                session.query(func.count(func.distinct(Sale.customer_id)))
                .filter(
                    func.date(Sale.date) >= start_date,
                    func.date(Sale.date) <= end_date,
                    Sale.customer_id.isnot(None),
                )
                .scalar()
                or 0
            )

            avg_order = Decimal(str(total_sales)) / Decimal(str(txn_count)) if txn_count > 0 else Decimal("0")

            return {
                "total_sales": Decimal(str(total_sales)),
                "txn_count": txn_count,
                "avg_order": avg_order,
                "items_sold": int(items_sold),
                "unique_customers": unique_customers,
            }

    @staticmethod
    def get_top_categories(start_date: date, end_date: date, limit: int = 6) -> list[dict]:
        """Top selling categories by revenue within a date range."""
        db = Database()
        with db.get_session() as session:
            rows = (
                session.query(
                    Category.name,
                    func.sum(SaleItem.subtotal).label("total"),
                )
                .join(Product, Product.category_id == Category.id)
                .join(SaleItem, SaleItem.product_id == Product.id)
                .join(Sale, SaleItem.sale_id == Sale.id)
                .filter(
                    func.date(Sale.date) >= start_date,
                    func.date(Sale.date) <= end_date,
                )
                .group_by(Category.id)
                .order_by(func.sum(SaleItem.subtotal).desc())
                .limit(limit)
                .all()
            )

            return [{"name": r[0] or "Uncategorized", "total": Decimal(str(r[1] or 0))} for r in rows]

    @staticmethod
    def get_top_customers(start_date: date, end_date: date, limit: int = 5) -> list[dict]:
        """Top customers by spend within a date range."""
        db = Database()
        with db.get_session() as session:
            rows = (
                session.query(
                    Customer.name,
                    func.sum(Sale.total_amount).label("total"),
                )
                .join(Sale, Sale.customer_id == Customer.id)
                .filter(
                    func.date(Sale.date) >= start_date,
                    func.date(Sale.date) <= end_date,
                )
                .group_by(Customer.id)
                .order_by(func.sum(Sale.total_amount).desc())
                .limit(limit)
                .all()
            )

            return [{"name": r[0], "total": Decimal(str(r[1] or 0))} for r in rows]

    # ------------------------------------------------------------------
    # Legacy helpers (kept for backward compatibility)
    # ------------------------------------------------------------------

    @staticmethod
    def get_recent_sales(limit: int = 10) -> list:
        """Last N completed sales with time, doc#, customer, payment, total."""
        db = Database()
        with db.get_session() as session:
            sales = (
                session.query(Sale)
                .options(
                    joinedload(Sale.customer),
                    joinedload(Sale.payments),
                )
                .order_by(Sale.date.desc())
                .limit(limit)
                .all()
            )

            results = []
            for sale in sales:
                payment_methods = ", ".join(p.payment_method for p in sale.payments) if sale.payments else "N/A"
                customer_name = sale.customer.name if sale.customer else "Walk-in"
                results.append(
                    {
                        "time": (sale.date.strftime("%H:%M") if sale.date else ""),
                        "doc_number": sale.document_number or "",
                        "customer": customer_name,
                        "payment": payment_methods,
                        "total": Decimal(str(sale.total_amount)),
                    }
                )
            return results

    @staticmethod
    def get_top_selling_today(limit: int = 5) -> list:
        """Top products by quantity sold today."""
        db = Database()
        with db.get_session() as session:
            today = date.today()

            rows = (
                session.query(
                    Product.name_en,
                    func.sum(SaleItem.qty).label("total_qty"),
                    func.sum(SaleItem.subtotal).label("total_revenue"),
                )
                .join(SaleItem, SaleItem.product_id == Product.id)
                .join(Sale, SaleItem.sale_id == Sale.id)
                .filter(func.date(Sale.date) == today)
                .group_by(Product.id)
                .order_by(func.sum(SaleItem.qty).desc())
                .limit(limit)
                .all()
            )

            return [
                {
                    "name": row[0],
                    "qty": int(row[1] or 0),
                    "revenue": Decimal(str(row[2] or 0)),
                }
                for row in rows
            ]

    @staticmethod
    def get_payment_breakdown() -> list:
        """Payment method totals for today."""
        db = Database()
        with db.get_session() as session:
            today = date.today()

            rows = (
                session.query(
                    SalePayment.payment_method,
                    func.sum(SalePayment.amount).label("total"),
                )
                .join(Sale, SalePayment.sale_id == Sale.id)
                .filter(func.date(Sale.date) == today)
                .group_by(SalePayment.payment_method)
                .order_by(func.sum(SalePayment.amount).desc())
                .all()
            )

            return [
                {
                    "method": row[0],
                    "total": Decimal(str(row[1] or 0)),
                }
                for row in rows
            ]
