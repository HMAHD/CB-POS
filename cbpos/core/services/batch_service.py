"""Batch and Expiry Tracking Domain Service (#926).

Implements FEFO (First-Expiry-First-Out) allocation, per-batch pricing, expiry date parsing,
concurrency locking, and synthetic opening batch generation.
"""

import calendar
import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case
from sqlalchemy.orm import Session, joinedload

from cbpos.core.database import Database
from cbpos.core.models import Product, ProductBatch


class ExpiredBatchError(ValueError):
    """Raised when an operation attempts to allocate or sell an expired batch without override."""

    def __init__(self, batch: ProductBatch, message: str | None = None):
        self.batch = batch
        super().__init__(message or f"Batch {batch.batch_no or '(no batch)'} expired on {batch.expiry_date}.")


class InsufficientStockError(ValueError):
    """Raised when insufficient unexpired batch stock is available."""


class BatchService:
    """Service managing ProductBatch domain operations and FEFO allocation."""

    @staticmethod
    def parse_mmyy_to_month_end(mmyy_str: str) -> date:
        """Parse an MM/YY or MM/YYYY string into a Date representing the last day of that month.

        Supports formats: 'MM/YY', 'MM-YY', 'MMYY', 'MM/YYYY', 'MM-YYYY'.
        Accurately handles February leap days.
        """
        raw = mmyy_str.strip()
        if not raw:
            raise ValueError("Expiry date string cannot be empty")

        month: int
        year: int

        # Check for separator
        if "/" in raw or "-" in raw:
            parts = [p.strip() for p in re.split(r"[/\\-]", raw) if p.strip()]
            if len(parts) != 2:
                raise ValueError(f"Invalid expiry format: {mmyy_str}")
            try:
                month = int(parts[0])
                year = int(parts[1])
            except ValueError as e:
                raise ValueError(f"Non-numeric expiry components: {mmyy_str}") from e
        elif raw.isdigit() and len(raw) in (4, 6):
            try:
                month = int(raw[:2])
                year = int(raw[2:])
            except ValueError as e:
                raise ValueError(f"Invalid numeric expiry string: {mmyy_str}") from e
        else:
            raise ValueError(f"Unrecognized expiry date format: {mmyy_str}")

        if not (1 <= month <= 12):
            raise ValueError(f"Expiry month must be between 1 and 12, got {month}")

        # Expand 2-digit year to 4-digit year
        if year < 100:
            year += 2000

        _, last_day = calendar.monthrange(year, month)
        return date(year, month, last_day)

    @staticmethod
    def get_batches_for_product(
        product_id: int,
        include_zero_stock: bool = False,
        session: Session | None = None,
    ) -> list[ProductBatch]:
        """Fetch active batches for a product in FEFO order:

        (expiry_date ASC NULLS LAST, received_at ASC, id ASC).
        """

        def _query(s: Session) -> list[ProductBatch]:
            query = s.query(ProductBatch).filter(
                ProductBatch.product_id == product_id,
                ProductBatch.is_active.is_(True),
            )
            if not include_zero_stock:
                query = query.filter(ProductBatch.qty_on_hand > 0)

            # Order: expiry_date ASC with NULLs last, then received_at ASC, then id ASC
            null_last_order = case(
                (ProductBatch.expiry_date.is_(None), 1),
                else_=0,
            )
            return query.order_by(
                null_last_order,
                ProductBatch.expiry_date.asc(),
                ProductBatch.received_at.asc(),
                ProductBatch.id.asc(),
            ).all()

        if session is not None:
            return _query(session)
        with Database().get_session() as s:
            return _query(s)

    @staticmethod
    def get_active_differing_mrps(
        product_id: int,
        session: Session | None = None,
    ) -> list[Decimal]:
        """Return distinct active MRP values on hand for a tracked product."""

        def _query(s: Session) -> list[Decimal]:
            rows = (
                s.query(ProductBatch.mrp)
                .distinct()
                .filter(
                    ProductBatch.product_id == product_id,
                    ProductBatch.is_active.is_(True),
                    ProductBatch.qty_on_hand > 0,
                    ProductBatch.mrp.is_not(None),
                )
                .order_by(ProductBatch.mrp.asc())
                .all()
            )
            return [Decimal(str(r[0])) for r in rows if r[0] is not None]

        if session is not None:
            return _query(session)
        with Database().get_session() as s:
            return _query(s)

    @staticmethod
    def requires_batch_picker(
        product_id: int,
        session: Session | None = None,
    ) -> bool:
        """True if the product has multiple active batches on shelf with differing MRPs."""
        mrps = BatchService.get_active_differing_mrps(product_id, session=session)
        return len(mrps) > 1

    @staticmethod
    def allocate_fefo_stock(
        product_id: int,
        requested_qty: Decimal,
        allow_negative_stock: bool = False,
        session: Session | None = None,
    ) -> list[tuple[ProductBatch, Decimal]]:
        """Allocate requested stock across unexpired active batches in strict FEFO order.

        Returns list of (batch, allocated_qty) tuples.
        If available unexpired stock is insufficient:
        - If allow_negative_stock=True: newest active batch absorbs overdraft balance.
        - If allow_negative_stock=False: raises InsufficientStockError.
        """
        if requested_qty <= Decimal("0.000"):
            return []

        def _allocate(s: Session) -> list[tuple[ProductBatch, Decimal]]:
            today = date.today()

            # Query candidate batches (unexpired, active, qty_on_hand > 0)
            null_last_order = case(
                (ProductBatch.expiry_date.is_(None), 1),
                else_=0,
            )
            candidate_query = (
                s.query(ProductBatch)
                .filter(
                    ProductBatch.product_id == product_id,
                    ProductBatch.is_active.is_(True),
                    ProductBatch.qty_on_hand > 0,
                    (ProductBatch.expiry_date >= today) | (ProductBatch.expiry_date.is_(None)),
                )
                .order_by(
                    null_last_order,
                    ProductBatch.expiry_date.asc(),
                    ProductBatch.received_at.asc(),
                    ProductBatch.id.asc(),
                )
            )

            # Concurrency row-locking in deterministic ascending ID order
            candidate_batches = candidate_query.all()
            if candidate_batches:
                candidate_ids = sorted(b.id for b in candidate_batches)
                locked_map = {
                    b.id: b
                    for b in s.query(ProductBatch)
                    .filter(ProductBatch.id.in_(candidate_ids))
                    .order_by(ProductBatch.id.asc())
                    .with_for_update()
                    .all()
                }
                candidate_batches = [locked_map[b.id] for b in candidate_batches]

            allocations: list[tuple[ProductBatch, Decimal]] = []
            remaining_qty = requested_qty

            for batch in candidate_batches:
                if remaining_qty <= Decimal("0.000"):
                    break
                take_qty = min(batch.qty_on_hand, remaining_qty)
                if take_qty > Decimal("0.000"):
                    allocations.append((batch, take_qty))
                    remaining_qty -= take_qty

            if remaining_qty > Decimal("0.000"):
                if not allow_negative_stock:
                    allocated_so_far = sum(qty for _, qty in allocations)
                    raise InsufficientStockError(
                        f"Insufficient unexpired stock for product {product_id}. "
                        f"Available: {allocated_so_far:.3f}, Requested: {requested_qty:.3f}"
                    )

                # Negative stock permitted: newest active batch absorbs overdraft
                newest_batch = (
                    s.query(ProductBatch)
                    .filter(
                        ProductBatch.product_id == product_id,
                        ProductBatch.is_active.is_(True),
                    )
                    .order_by(
                        ProductBatch.received_at.desc(),
                        ProductBatch.id.desc(),
                    )
                    .first()
                )
                if newest_batch is not None and newest_batch.id not in [b.id for b in candidate_batches]:
                    newest_batch = (
                        s.query(ProductBatch).filter(ProductBatch.id == newest_batch.id).with_for_update().first()
                    )

                if newest_batch is not None:
                    # Check if already in allocations
                    found = False
                    for i, (b, q) in enumerate(allocations):
                        if b.id == newest_batch.id:
                            allocations[i] = (b, q + remaining_qty)
                            found = True
                            break
                    if not found:
                        allocations.append((newest_batch, remaining_qty))
                else:
                    # Product has no active batches at all -> create overdraft batch
                    overdraft_batch = ProductBatch(
                        product_id=product_id,
                        batch_no="OVERDRAFT",
                        expiry_date=None,
                        qty_on_hand=Decimal("0.000"),
                        is_active=True,
                    )
                    s.add(overdraft_batch)
                    s.flush()
                    allocations.append((overdraft_batch, remaining_qty))

            return allocations

        if session is not None:
            return _allocate(session)
        with Database().get_session() as s:
            return _allocate(s)

    @staticmethod
    def validate_batch_allocation(
        product_id: int,
        batch_id: int,
        requested_qty: Decimal,
        allow_expired: bool = False,
        session: Session | None = None,
    ) -> ProductBatch:
        """Validate and lock an explicit batch selection for a sale.

        Rejects expired batches unless allow_expired=True (manager override).
        """

        def _validate(s: Session) -> ProductBatch:
            batch = s.query(ProductBatch).filter(ProductBatch.id == batch_id).with_for_update().first()
            if batch is None:
                raise ValueError(f"Batch {batch_id} not found")
            if batch.product_id != product_id:
                raise ValueError(f"Batch {batch_id} belongs to product {batch.product_id}, not {product_id}")

            if batch.is_expired and not allow_expired:
                raise ExpiredBatchError(batch)

            return batch

        if session is not None:
            return _validate(session)
        with Database().get_session() as s:
            return _validate(s)

    @staticmethod
    def create_synthetic_opening_batch(
        product: Product,
        session: Session,
    ) -> ProductBatch | None:
        """Generate a synthetic opening batch when tracking is enabled for a product with non-zero stock.

        Preserves invariant: sum(batch.qty_on_hand) == product.stock_qty.
        """
        if not product.tracks_batches:
            return None

        # Check if batches already exist
        existing = session.query(ProductBatch.id).filter(ProductBatch.product_id == product.id).first()
        if existing is not None:
            return None

        opening = ProductBatch(
            product_id=product.id,
            batch_no="OPENING",
            expiry_date=None,
            qty_on_hand=Decimal(str(product.stock_qty or 0)),
            cost=Decimal(str(product.cost or 0)),
            mrp=Decimal(str(product.price or 0)),
            is_active=True,
        )
        session.add(opening)
        session.flush()
        return opening

    @staticmethod
    def get_expiring_batches(
        days_ahead: int = 30,
        session: Session | None = None,
    ) -> list[ProductBatch]:
        """Fetch active batches expiring within `days_ahead` days."""

        def _query(s: Session) -> list[ProductBatch]:
            cutoff = date.today() + timedelta(days=days_ahead)
            return (
                s.query(ProductBatch)
                .filter(
                    ProductBatch.is_active.is_(True),
                    ProductBatch.qty_on_hand > 0,
                    ProductBatch.expiry_date.is_not(None),
                    ProductBatch.expiry_date <= cutoff,
                )
                .order_by(
                    ProductBatch.expiry_date.asc(),
                    ProductBatch.qty_on_hand.desc(),
                )
                .all()
            )

        if session is not None:
            return _query(session)
        with Database().get_session() as s:
            return _query(s)

    @staticmethod
    def get_expiring_batches_summary(session: Session | None = None) -> dict[str, int]:
        """Return counts of batches that are expired, or expiring within 30, 60, 90 days (#926)."""

        def _query(s: Session) -> dict[str, int]:
            today = date.today()
            cutoff_30 = today + timedelta(days=30)
            cutoff_60 = today + timedelta(days=60)
            cutoff_90 = today + timedelta(days=90)

            active_q = s.query(ProductBatch).filter(
                ProductBatch.is_active.is_(True),
                ProductBatch.qty_on_hand > 0,
                ProductBatch.expiry_date.is_not(None),
            )
            expired = active_q.filter(ProductBatch.expiry_date < today).count()
            in_30 = active_q.filter(ProductBatch.expiry_date >= today, ProductBatch.expiry_date <= cutoff_30).count()
            in_60 = active_q.filter(ProductBatch.expiry_date >= today, ProductBatch.expiry_date <= cutoff_60).count()
            in_90 = active_q.filter(ProductBatch.expiry_date >= today, ProductBatch.expiry_date <= cutoff_90).count()

            return {
                "expired": expired,
                "expiring_30": in_30,
                "expiring_60": in_60,
                "expiring_90": in_90,
                "total_actionable": expired + in_30,
            }

        if session is not None:
            return _query(session)
        with Database().get_session() as s:
            return _query(s)

    @staticmethod
    def get_expiring_batches_by_filter(
        filter_mode: str = "30",
        session: Session | None = None,
    ) -> list[ProductBatch]:
        """Fetch active batches filtered by horizon: '30', '60', '90', or 'expired' (#926)."""

        def _query(s: Session) -> list[ProductBatch]:
            today = date.today()
            q = (
                s.query(ProductBatch)
                .options(joinedload(ProductBatch.product))
                .filter(
                    ProductBatch.is_active.is_(True),
                    ProductBatch.qty_on_hand > 0,
                    ProductBatch.expiry_date.is_not(None),
                )
            )
            if filter_mode == "expired":
                q = q.filter(ProductBatch.expiry_date < today)
            elif filter_mode == "60":
                cutoff = today + timedelta(days=60)
                q = q.filter(ProductBatch.expiry_date >= today, ProductBatch.expiry_date <= cutoff)
            elif filter_mode == "90":
                cutoff = today + timedelta(days=90)
                q = q.filter(ProductBatch.expiry_date >= today, ProductBatch.expiry_date <= cutoff)
            else:  # "30" or default
                cutoff = today + timedelta(days=30)
                q = q.filter(ProductBatch.expiry_date >= today, ProductBatch.expiry_date <= cutoff)

            batches = q.order_by(ProductBatch.expiry_date.asc(), ProductBatch.qty_on_hand.desc()).all()
            if session is None:
                for b in batches:
                    _ = b.product
                    s.expunge(b)
            return batches

        if session is not None:
            return _query(session)
        with Database().get_session() as s:
            return _query(s)
