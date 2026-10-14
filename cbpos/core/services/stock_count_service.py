"""Service for managing physical stock take (count → compare → adjust) workflow."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, update
from sqlalchemy.orm import joinedload

from cbpos.core.constants.status import DocumentStatus, Precision
from cbpos.core.database import Database
from cbpos.core.models import Product, StockCount, StockCountItem
from cbpos.core.services.document_service import DocumentService
from cbpos.core.services.stock_service import StockService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VarianceTotals:
    """A stock count's two value-variance figures (#644).

    Attributes:
        net: Signed sum of every line's variance value -- surpluses minus
            shortages. +500 and -500 give 0.
        discrepancy: Sum of the absolute variance values -- how far the
            shelf is from the records in total. +500 and -500 give 1,000.
            This is what ``StockCount.total_variance_value`` stores.
    """

    net: Decimal
    discrepancy: Decimal


class StockCountService:
    """Service for physical stock count lifecycle."""

    @staticmethod
    def variance_totals(items: Iterable[StockCountItem]) -> VarianceTotals:
        """
        Net variance and total discrepancy of stock count lines, at cost.

        The single place both figures are computed, so every screen shows
        the same numbers (#644). Lines not counted yet (no variance value)
        are skipped.

        Args:
            items: Stock count lines (anything with ``variance_value``).

        Returns:
            VarianceTotals with ``net`` and ``discrepancy``, rounded to money.
        """
        values = [item.variance_value for item in items if item.variance_value is not None]
        net = sum(values, Decimal("0"))
        discrepancy = sum((abs(value) for value in values), Decimal("0"))
        return VarianceTotals(net=net.quantize(Precision.MONEY), discrepancy=discrepancy.quantize(Precision.MONEY))

    @staticmethod
    def create_stock_count(user_id: int, note: str | None = None) -> StockCount:
        """
        Create a new stock count document in DRAFT status.

        Args:
            user_id: User initiating the count.
            note: Optional description/note for this count.

        Returns:
            The created StockCount document.
        """
        document_number = DocumentService.generate_number("STOCK_COUNT")

        db = Database()
        with db.get_session() as session:
            stock_count = StockCount(
                document_number=document_number,
                type="stock_count",
                date=datetime.now(),
                user_id=user_id,
                status=DocumentStatus.DRAFT,
                note=note,
                total_variance_value=Decimal("0.00"),
            )
            session.add(stock_count)
            session.commit()
            session.refresh(stock_count)
            return stock_count

    @staticmethod
    def add_all_products(stock_count_id: int, category_id: int | None = None) -> int:
        """
        Snapshot current stock for all active products as expected quantities.

        Args:
            stock_count_id: The stock count to add items to.
            category_id: Optional filter by category.

        Returns:
            Number of items added.
        """
        db = Database()
        with db.get_session() as session:
            stock_count = session.get(StockCount, stock_count_id)
            if not stock_count or stock_count.status != DocumentStatus.DRAFT:
                raise ValueError("Stock count not found or not in DRAFT status.")

            # Get existing product IDs in this count (select only the column needed)
            existing_ids = {
                row[0]
                for row in session.query(StockCountItem.product_id)
                .filter(StockCountItem.stock_count_id == stock_count_id)
                .all()
            }

            query = session.query(Product).filter(
                Product.is_active.is_(True),
                Product.is_service.is_(False),
            )
            if category_id:
                query = query.filter(Product.category_id == category_id)

            products = query.all()
            count = 0

            for product in products:
                if product.id in existing_ids:
                    continue

                item = StockCountItem(
                    stock_count_id=stock_count_id,
                    product_id=product.id,
                    expected_qty=product.stock_qty,
                )
                session.add(item)
                count += 1

            session.commit()
            logger.info(
                "Added %d products to stock count %s",
                count,
                stock_count.document_number,
            )
            return count

    @staticmethod
    def add_single_item(stock_count_id: int, product_id: int) -> StockCountItem:
        """
        Add a single product to the stock count (e.g. via barcode scan).

        Args:
            stock_count_id: Stock count document ID.
            product_id: Product to add.

        Returns:
            The created StockCountItem.

        Raises:
            ValueError: If product already in count, count not in DRAFT, or
                the product is a service (services carry no stock, so
                ``add_all_products`` leaves them out too).
        """
        db = Database()
        with db.get_session() as session:
            stock_count = session.get(StockCount, stock_count_id)
            if not stock_count or stock_count.status != DocumentStatus.DRAFT:
                raise ValueError("Stock count not found or not in DRAFT status.")

            existing = (
                session.query(StockCountItem).filter_by(stock_count_id=stock_count_id, product_id=product_id).first()
            )
            if existing:
                raise ValueError("Product already in this stock count.")

            product = session.get(Product, product_id)
            if not product:
                raise ValueError("Product not found.")
            if product.is_service:
                raise ValueError("Service items are not stock-counted.")

            item = StockCountItem(
                stock_count_id=stock_count_id,
                product_id=product_id,
                expected_qty=product.stock_qty,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    @staticmethod
    def update_count(item_id: int, counted_qty: Decimal) -> StockCountItem:
        """
        Set the counted quantity for an item and calculate variance.

        Args:
            item_id: StockCountItem ID.
            counted_qty: Physical count entered by user.

        Returns:
            Updated StockCountItem with variance calculated.
        """
        db = Database()
        with db.get_session() as session:
            item = session.get(StockCountItem, item_id)
            if not item:
                raise ValueError("Stock count item not found.")

            item.counted_qty = counted_qty.quantize(Precision.QUANTITY)
            item.variance_qty = (item.counted_qty - item.expected_qty).quantize(Precision.QUANTITY)

            # Calculate variance value using product cost
            product = session.get(Product, item.product_id)
            if product:
                item.variance_value = (item.variance_qty * product.cost).quantize(Precision.MONEY)
            else:
                item.variance_value = Decimal("0.00")

            session.commit()
            session.refresh(item)
            return item

    @staticmethod
    def increment_count(item_id: int, by: Decimal) -> StockCountItem:
        """
        Add ``by`` to an item's counted quantity (uncounted counts as 0).

        Used when a product already in the count is scanned or added again,
        so it is counted up instead of rejected (#615). The addition runs in
        SQL against the stored count, so a count saved meanwhile (a quick
        second scan, another terminal) is added to, never overwritten with
        a stale value plus ``by`` (#548).

        Args:
            item_id: StockCountItem ID.
            by: Quantity to add to the current count.

        Returns:
            Updated StockCountItem with variance recalculated.

        Raises:
            ValueError: If the item is missing or its count is not in DRAFT.
        """
        db = Database()
        with db.get_session() as session:
            item = session.get(StockCountItem, item_id)
            if not item:
                raise ValueError("Stock count item not found.")

            stock_count = session.get(StockCount, item.stock_count_id)
            if not stock_count or stock_count.status != DocumentStatus.DRAFT:
                raise ValueError("Stock count not found or not in DRAFT status.")

            session.execute(
                update(StockCountItem)
                .where(StockCountItem.id == item_id)
                .values(counted_qty=func.coalesce(StockCountItem.counted_qty, 0) + by)
                .execution_options(synchronize_session=False)
            )
            session.refresh(item)
            item.counted_qty = Decimal(item.counted_qty).quantize(Precision.QUANTITY)
            item.variance_qty = (item.counted_qty - item.expected_qty).quantize(Precision.QUANTITY)

            product = session.get(Product, item.product_id)
            if product:
                item.variance_value = (item.variance_qty * product.cost).quantize(Precision.MONEY)
            else:
                item.variance_value = Decimal("0.00")

            session.commit()
            session.refresh(item)
            return item

    @staticmethod
    def remove_item(item_id: int) -> bool:
        """
        Remove an uncounted item from the stock count.

        Args:
            item_id: StockCountItem ID.

        Returns:
            True if removed.
        """
        db = Database()
        with db.get_session() as session:
            item = session.get(StockCountItem, item_id)
            if not item:
                raise ValueError("Stock count item not found.")

            stock_count = session.get(StockCount, item.stock_count_id)
            if stock_count and stock_count.status != DocumentStatus.DRAFT:
                raise ValueError("Cannot remove items from a finalized count.")

            session.delete(item)
            session.commit()
            return True

    @staticmethod
    def finalize_count(stock_count_id: int) -> StockCount:
        """
        Finalize the count: validate all items are counted, calculate variances,
        and set status to COUNTED.

        Args:
            stock_count_id: Stock count document ID.

        Returns:
            The finalized StockCount.

        Raises:
            ValueError: If any items are not yet counted.
        """
        db = Database()
        with db.get_session() as session:
            stock_count = session.get(
                StockCount,
                stock_count_id,
                options=[joinedload(StockCount.items).joinedload(StockCountItem.product)],
            )
            if not stock_count:
                raise ValueError("Stock count not found.")
            if stock_count.status != DocumentStatus.DRAFT:
                raise ValueError("Stock count is not in DRAFT status.")

            if not stock_count.items:
                raise ValueError("No items in stock count.")

            # Validate all items have been counted
            uncounted = [item for item in stock_count.items if item.counted_qty is None]
            if uncounted:
                raise ValueError(f"{len(uncounted)} item(s) have not been counted yet.")

            # Recalculate all variances
            for item in stock_count.items:
                item.variance_qty = (item.counted_qty - item.expected_qty).quantize(Precision.QUANTITY)
                if item.product:
                    item.variance_value = (item.variance_qty * item.product.cost).quantize(Precision.MONEY)
                else:
                    item.variance_value = Decimal("0.00")

            stock_count.total_variance_value = StockCountService.variance_totals(stock_count.items).discrepancy
            stock_count.status = DocumentStatus.COUNTED

            session.commit()
            session.refresh(stock_count)
            logger.info(
                "Stock count %s finalized. Total variance: %s",
                stock_count.document_number,
                stock_count.total_variance_value,
            )
            return stock_count

    @staticmethod
    def approve_and_apply(stock_count_id: int, user_id: int) -> StockCount:
        """
        Approve the count and apply stock adjustments.
        For each item with variance != 0, record a stock movement (ADJUSTMENT).

        Args:
            stock_count_id: Stock count document ID.
            user_id: User approving the count.

        Returns:
            The completed StockCount.
        """
        db = Database()
        with db.get_session() as session:
            stock_count = session.get(StockCount, stock_count_id, options=[joinedload(StockCount.items)])
            if not stock_count:
                raise ValueError("Stock count not found.")
            if stock_count.status != DocumentStatus.COUNTED:
                raise ValueError("Stock count must be in COUNTED status to approve.")

            for item in stock_count.items:
                if item.variance_qty and item.variance_qty != 0:
                    StockService.record_movement(
                        product_id=item.product_id,
                        qty_change=item.variance_qty,
                        movement_type="ADJUSTMENT",
                        user_id=user_id,
                        document_id=stock_count.id,
                        session=session,
                    )

            stock_count.total_variance_value = StockCountService.variance_totals(stock_count.items).discrepancy
            stock_count.status = DocumentStatus.COMPLETED

            session.commit()
            session.refresh(stock_count)
            logger.info(
                "Stock count %s approved and applied by user %d.",
                stock_count.document_number,
                user_id,
            )
            return stock_count

    @staticmethod
    def void_stock_count(stock_count_id: int) -> StockCount:
        """
        Void a stock count. Only DRAFT or COUNTED counts can be voided.

        Args:
            stock_count_id: Stock count document ID.

        Returns:
            The voided StockCount.
        """
        db = Database()
        with db.get_session() as session:
            stock_count = session.get(StockCount, stock_count_id)
            if not stock_count:
                raise ValueError("Stock count not found.")
            if stock_count.status not in (
                DocumentStatus.DRAFT,
                DocumentStatus.COUNTED,
            ):
                raise ValueError("Only DRAFT or COUNTED counts can be voided.")

            stock_count.status = DocumentStatus.VOID
            session.commit()
            session.refresh(stock_count)
            return stock_count

    @staticmethod
    def get_stock_count(stock_count_id: int) -> StockCount | None:
        """Get a stock count with eager-loaded items and products."""
        db = Database()
        with db.get_session() as session:
            stock_count = session.get(
                StockCount,
                stock_count_id,
                options=[
                    joinedload(StockCount.items).joinedload(StockCountItem.product),
                    joinedload(StockCount.user),
                ],
            )
            if stock_count:
                session.expunge(stock_count)
            return stock_count

    @staticmethod
    def get_all_stock_counts(
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[StockCount]:
        """
        Get stock count history with optional filters.

        Args:
            status: Filter by status.
            date_from: Filter from date.
            date_to: Filter to date.

        Returns:
            List of StockCount objects ordered by date descending.
        """
        db = Database()
        with db.get_session() as session:
            query = session.query(StockCount).options(
                joinedload(StockCount.items),
                joinedload(StockCount.user),
            )

            if status:
                query = query.filter(StockCount.status == status)
            if date_from:
                query = query.filter(StockCount.date >= date_from)
            if date_to:
                query = query.filter(StockCount.date <= date_to)

            counts = query.order_by(StockCount.date.desc()).all()
            for c in counts:
                session.expunge(c)
            return counts
