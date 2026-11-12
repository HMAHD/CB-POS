import logging
from datetime import datetime

from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import (
    Customer,
    Sale,
    SaleItem,
)
from cbpos.core.utils.date_ranges import range_for
from cbpos.core.utils.formatters import escape_like

logger = logging.getLogger(__name__)


class SaleQueryService:
    """
    Read-only service for querying sales data.
    Provides methods for fetching sale history, details, and recent sales.
    """

    @staticmethod
    def get_last_sale() -> Sale:
        """Return the most recent sale, detached from session."""
        db = Database()
        with db.get_session() as session:
            sale = (
                session.query(Sale)
                .options(
                    joinedload(Sale.items).joinedload(SaleItem.product),
                    joinedload(Sale.user),
                    joinedload(Sale.customer),
                    joinedload(Sale.payments),
                )
                .order_by(Sale.id.desc())
                .first()
            )
            if sale:
                _ = sale.customer
                _ = sale.user
                for it in sale.items:
                    _ = it.product
                    _ = it.warranties
                _ = sale.payments
                session.expunge_all()
            return sale

    @staticmethod
    def get_sales_history(
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        search_term: str = None,
        limit: int = 500,
    ) -> list:
        """
        Fetch sales within a date range with optional search filter.

        Args:
            from_date: Optional start datetime
            to_date: Optional end datetime
            search_term: Optional receipt# or customer name/phone filter
            limit: Maximum number of results (default 500)

        Returns:
            List of detached Sale objects with eager-loaded relationships
        """
        start_dt, end_dt = range_for(from_date, to_date)
        db = Database()
        with db.get_session() as session:
            query = session.query(Sale)
            if start_dt is not None:
                query = query.filter(Sale.date >= start_dt)
            if end_dt is not None:
                query = query.filter(Sale.date < end_dt)

            if search_term:
                term = f"%{escape_like(search_term)}%"
                query = query.filter(
                    (Sale.document_number.like(term))
                    | (Sale.customer.has(Customer.name.ilike(term)))
                    | (Sale.customer.has(Customer.phone.like(term)))
                )

            sales = (
                query.options(
                    joinedload(Sale.user),
                    joinedload(Sale.customer),
                    joinedload(Sale.items).joinedload(SaleItem.product),
                    joinedload(Sale.payments),
                )
                .order_by(Sale.date.desc())
                .limit(limit)
                .all()
            )

            # Detach from session
            for sale in sales:
                session.expunge(sale)

            return sales

    @staticmethod
    def get_sale_details(sale_id: int) -> Sale:
        """
        Fetch a single sale with all relationships loaded.

        Args:
            sale_id: Sale ID to fetch

        Returns:
            Detached Sale object or None
        """
        db = Database()
        with db.get_session() as session:
            sale = session.get(
                Sale,
                sale_id,
                options=[
                    joinedload(Sale.items).joinedload(SaleItem.product),
                    joinedload(Sale.user),
                    joinedload(Sale.customer),
                    joinedload(Sale.payments),
                ],
            )
            if sale:
                _ = sale.customer
                _ = sale.user
                for it in sale.items:
                    _ = it.product
                    _ = it.warranties
                _ = sale.payments
                session.expunge_all()
            return sale
