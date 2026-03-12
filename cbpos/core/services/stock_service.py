import logging
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from cbpos.core.constants.status import MovementType
from cbpos.core.database import Database
from cbpos.core.models import Product, StockMovement

logger = logging.getLogger(__name__)

_VALID_MOVEMENT_TYPES = frozenset(
    {
        MovementType.SALE,
        MovementType.PURCHASE,
        MovementType.ADJUSTMENT,
        MovementType.RETURN,
        MovementType.VOID,
    }
)


class StockService:
    @staticmethod
    def record_movement(
        product_id: int,
        qty_change: Decimal,
        movement_type: str,
        user_id: int,
        document_id: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> Optional[StockMovement]:
        """
        Record a stock movement and update product quantity.
        Atomic operation with negative stock validation.
        """
        if movement_type not in _VALID_MOVEMENT_TYPES:
            raise ValueError(
                "Invalid movement type '{0}'. Must be one of: {1}".format(
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
            )

    @staticmethod
    def _execute_movement(
        session: Session,
        product_id: int,
        qty_change: Decimal,
        movement_type: str,
        user_id: int,
        document_id: Optional[int],
        commit: bool,
    ) -> Optional[StockMovement]:
        product = session.get(Product, product_id)
        if not product:
            raise ValueError("Product {0} not found".format(product_id))

        # Skip inventory tracking for service items
        if product.is_service:
            return None

        # Check for negative stock (if deducting)
        if qty_change < 0:
            from cbpos.core.services.config_service import ConfigService

            config = ConfigService.get_all()
            allow_negative = config.get("allow_negative_stock", False)

            new_balance = product.stock_qty + qty_change
            if not allow_negative and new_balance < 0:
                raise ValueError(
                    "Insufficient Stock: {0} (Available: {1:.3f}, Required: {2:.3f})".format(
                        product.name_en,
                        product.stock_qty,
                        abs(qty_change),
                    )
                )

        # Update Stock
        product.stock_qty += qty_change

        # Create Movement Record
        movement = StockMovement(
            product_id=product_id,
            user_id=user_id,
            qty_change=qty_change,
            balance_after=product.stock_qty,
            document_id=document_id,
            type=movement_type,
        )
        session.add(movement)

        if commit:
            session.commit()
            session.refresh(movement)
        else:
            session.flush()

        return movement

    @staticmethod
    def get_history(product_id: int, limit: int = 500) -> List[StockMovement]:
        """Get stock movement history for a product."""
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(StockMovement)
                .where(StockMovement.product_id == product_id)
                .order_by(StockMovement.timestamp.desc())
                .limit(limit)
            )
            results = list(session.scalars(stmt).all())
            for r in results:
                session.expunge(r)
            return results

    @staticmethod
    def get_reorder_list() -> List[Product]:
        """Get list of products that need reordering."""
        db = Database()
        with db.get_session() as session:
            stmt = select(Product).where(
                Product.is_active.is_(True),
                Product.is_service.is_(False),
                Product.stock_qty <= Product.reorder_point,
            )
            return list(session.scalars(stmt).all())
