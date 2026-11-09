import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.status import MovementType
from cbpos.core.database import Database
from cbpos.core.models import Product, StockMovement
from cbpos.core.services.product_service import ProductService

logger = logging.getLogger(__name__)

_VALID_MOVEMENT_TYPES = frozenset(
    {
        MovementType.SALE,
        MovementType.PURCHASE,
        MovementType.ADJUSTMENT,
        MovementType.RETURN,
        MovementType.VOID,
        MovementType.OPENING,
    }
)


@dataclass(frozen=True)
class ReorderRow:
    """Row representing a product needing reordering with its resolved supplier."""

    product_id: int
    name_en: str
    barcode: str
    stock_qty: Decimal
    reorder_point: Decimal
    preferred_qty: Decimal
    supplier_id: int | None
    supplier_name: str | None

    @property
    def id(self) -> int:
        """Return the product ID."""
        return self.product_id


class StockService:
    """Records stock movements (sale, purchase, adjustment, return, void) and keeps
    `Product.stock_qty` in sync, enforcing the negative-stock policy."""

    @staticmethod
    def record_movement(
        product_id: int,
        qty_change: Decimal,
        movement_type: str,
        user_id: int,
        document_id: int | None = None,
        session: Session | None = None,
        enforce_non_negative: bool = True,
    ) -> StockMovement | None:
        """
        Record a stock movement and update product quantity.
        Atomic operation with negative stock validation.
        """
        if movement_type not in _VALID_MOVEMENT_TYPES:
            raise ValueError(
                "Invalid movement type '{}'. Must be one of: {}".format(
                    movement_type, ", ".join(sorted(_VALID_MOVEMENT_TYPES))
                )
            )

        if session:
            return StockService._execute_movement(
                session,
                product_id,
                qty_change,
                movement_type,
                user_id,
                document_id,
                commit=False,
                enforce_non_negative=enforce_non_negative,
            )

        db = Database()
        with db.get_session() as db_session:
            return StockService._execute_movement(
                db_session,
                product_id,
                qty_change,
                movement_type,
                user_id,
                document_id,
                commit=True,
                enforce_non_negative=enforce_non_negative,
            )

    @staticmethod
    def _execute_movement(
        session: Session,
        product_id: int,
        qty_change: Decimal,
        movement_type: str,
        user_id: int,
        document_id: int | None,
        commit: bool,
        enforce_non_negative: bool = True,
    ) -> StockMovement | None:
        product = session.get(Product, product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        # Skip inventory tracking for service items
        if product.is_service:
            return None

        # Check for negative stock (if deducting)
        if qty_change < 0 and enforce_non_negative:
            from cbpos.core.services.config_service import ConfigService

            config = ConfigService.get_all()
            allow_negative = config.get("allow_negative_stock", False)

            new_balance = product.stock_qty + qty_change
            if not allow_negative and new_balance < 0:
                raise ValueError(
                    f"Insufficient Stock: {product.name_en} (Available: {product.stock_qty:.3f}, Required: {abs(qty_change):.3f})"
                )

        # Update Stock
        product.stock_qty += qty_change

        # Create Movement Record
        from cbpos.core.services.config_service import ConfigService

        movement = StockMovement(
            product_id=product_id,
            user_id=user_id,
            qty_change=qty_change,
            balance_after=product.stock_qty,
            document_id=document_id,
            type=movement_type,
            terminal_id=ConfigService.get("terminal_id") or "TERM-01",
        )
        session.add(movement)

        if commit:
            session.commit()
            session.refresh(movement)
        else:
            session.flush()

        return movement

    @staticmethod
    def get_history(product_id: int, limit: int = 500) -> list[StockMovement]:
        """Get stock movement history for a product, newest first.

        Args:
            product_id: Product whose movements to fetch.
            limit: Maximum number of rows to return.

        Returns:
            Detached movements with ``user`` and ``document`` eager-loaded.
        """
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(StockMovement)
                .where(StockMovement.product_id == product_id)
                .options(joinedload(StockMovement.user), joinedload(StockMovement.document))
                .order_by(StockMovement.timestamp.desc())
                .limit(limit)
            )
            results = list(session.scalars(stmt).all())
            for r in results:
                session.expunge(r)
            return results

    @staticmethod
    def get_reorder_rows() -> list[ReorderRow]:
        """Get list of products that need reordering with resolved suppliers.

        Supplier is resolved as default_supplier or the first associated supplier.
        """
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(Product)
                .where(
                    Product.is_active.is_(True),
                    ProductService.stock_tracked(),
                    Product.stock_qty <= Product.reorder_point,
                )
                .options(
                    joinedload(Product.default_supplier),
                    joinedload(Product.suppliers),
                )
            )
            products = list(session.scalars(stmt).unique().all())
            rows: list[ReorderRow] = []
            for p in products:
                supplier = p.default_supplier or (p.suppliers[0] if p.suppliers else None)
                rows.append(
                    ReorderRow(
                        product_id=p.id,
                        name_en=p.name_en,
                        barcode=p.barcode,
                        stock_qty=Decimal(str(p.stock_qty)),
                        reorder_point=Decimal(str(p.reorder_point)),
                        preferred_qty=Decimal(str(p.preferred_qty)),
                        supplier_id=supplier.id if supplier else None,
                        supplier_name=supplier.company_name if supplier else None,
                    )
                )
            return rows

    @staticmethod
    def get_reorder_list() -> list[Product]:
        """Get list of products that need reordering."""
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(Product)
                .where(
                    Product.is_active.is_(True),
                    ProductService.stock_tracked(),
                    Product.stock_qty <= Product.reorder_point,
                )
                .options(
                    joinedload(Product.default_supplier),
                    joinedload(Product.suppliers),
                )
            )
            products = list(session.scalars(stmt).unique().all())
            for p in products:
                session.expunge(p)
            return products
