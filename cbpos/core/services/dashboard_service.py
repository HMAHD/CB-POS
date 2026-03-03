from decimal import Decimal
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import Sale, Product, Shift, SaleItem, SalePayment
from cbpos.core.constants.status import ShiftStatus


class DashboardService:
    @staticmethod
    def get_kpis() -> dict:
        """
        Fetch Key Performance Indicators for the Dashboard.
        Includes total_sales, txn_count, items_sold, avg_sale,
        low_stock_count, and active_staff.
        """
        db = Database()
        with db.get_session() as session:
            today = date.today()

            # 1. Total Sales (Today)
            total_sales = session.query(func.sum(Sale.total_amount)).filter(
                func.date(Sale.date) == today
            ).scalar() or Decimal("0")

            # 2. Transaction Count (Today)
            txn_count = session.query(func.count(Sale.id)).filter(func.date(Sale.date) == today).scalar() or 0

            # 3. Items Sold (Today) — sum of SaleItem.qty
            items_sold = session.query(func.sum(SaleItem.qty)).join(Sale, SaleItem.sale_id == Sale.id).filter(
                func.date(Sale.date) == today
            ).scalar() or Decimal("0")

            # 4. Average Sale
            avg_sale = Decimal(str(total_sales)) / Decimal(str(txn_count)) if txn_count > 0 else Decimal("0")

            # 5. Low Stock Count
            low_stock_count = (
                session.query(func.count(Product.id))
                .filter(Product.is_active)
                .filter(Product.stock_qty <= Product.reorder_point)
                .scalar()
                or 0
            )

            # 6. Active Staff (Open Shifts)
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
        """
        Fetch KPIs for yesterday — used for trend % calculation.
        """
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

    @staticmethod
    def get_recent_sales(limit: int = 10) -> list:
        """
        Last N completed sales with time, doc#, customer name,
        payment method, and total.
        """
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
                        "time": sale.date.strftime("%H:%M") if sale.date else "",
                        "doc_number": sale.document_number or "",
                        "customer": customer_name,
                        "payment": payment_methods,
                        "total": Decimal(str(sale.total_amount)),
                    }
                )
            return results

    @staticmethod
    def get_top_selling_today(limit: int = 5) -> list:
        """
        Top products by quantity sold today with name, qty, and revenue.
        """
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
        """
        Payment method totals for today from SalePayment.
        """
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
