"""
Data export service for CB-POS.

Builds pandas DataFrames from database tables for export
to CSV, Excel, or PDF via ExportService.
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import Product, Customer, Sale

logger = logging.getLogger(__name__)


class DataExportService:
    """Builds DataFrames of business data for export."""

    @staticmethod
    def get_products_dataframe() -> pd.DataFrame:
        """
        Get all active products with category and unit names.

        Returns:
            DataFrame with columns: Barcode, Name, Price, Cost, Stock, Category, Unit.
        """
        db = Database()
        with db.get_session() as session:
            products = (
                session.query(Product)
                .options(
                    joinedload(Product.category),
                    joinedload(Product.unit),
                )
                .filter(Product.is_active.is_(True))
                .order_by(Product.name_en)
                .all()
            )

            rows = []
            for p in products:
                rows.append(
                    {
                        "Barcode": p.barcode,
                        "Name": p.name_en,
                        "Price": float(p.price),
                        "Cost": float(p.cost),
                        "Stock": float(p.stock_qty),
                        "Category": p.category.name if p.category else "",
                        "Unit": p.unit.name if p.unit else "pcs",
                    }
                )

        return pd.DataFrame(rows)

    @staticmethod
    def get_customers_dataframe() -> pd.DataFrame:
        """
        Get all active customers.

        Returns:
            DataFrame with columns: Name, Company, Phone, Email, Credit Limit, Current Debt.
        """
        db = Database()
        with db.get_session() as session:
            customers = session.query(Customer).filter(Customer.is_active.is_(True)).order_by(Customer.name).all()

            rows = []
            for c in customers:
                rows.append(
                    {
                        "Name": c.name,
                        "Company": c.company_name or "",
                        "Phone": c.phone or "",
                        "Email": c.email or "",
                        "Credit Limit": float(c.credit_limit),
                        "Current Debt": float(c.current_debt),
                    }
                )

        return pd.DataFrame(rows)

    @staticmethod
    def get_sales_dataframe(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get sales with optional date range filter.

        Args:
            start_date: Filter sales on or after this date.
            end_date: Filter sales on or before this date.

        Returns:
            DataFrame with columns: Invoice, Date, Customer, Total, Payment, Status.
        """
        db = Database()
        with db.get_session() as session:
            query = session.query(Sale).options(joinedload(Sale.customer)).order_by(Sale.date.desc())

            if start_date:
                query = query.filter(Sale.date >= start_date)
            if end_date:
                query = query.filter(Sale.date <= end_date)

            sales = query.all()

            rows = []
            for s in sales:
                rows.append(
                    {
                        "Invoice": s.document_number,
                        "Date": s.date.strftime("%Y-%m-%d %H:%M") if s.date else "",
                        "Customer": s.customer.name if s.customer else "Walk-in",
                        "Total": float(s.total_amount),
                        "VAT": float(s.tax_vat),
                        "Payment": s.payment_method,
                        "Status": s.status,
                    }
                )

        return pd.DataFrame(rows)
