from decimal import Decimal
from typing import List, Optional
from sqlalchemy import select
from cbpos.core.database import get_db_session
from cbpos.core.models import Product, StockMovement


class StockService:
    @staticmethod
    def record_movement(
        product_id: int,
        qty_change: Decimal,
        movement_type: str,
        reference: str,
        user_id: int,
    ) -> Optional[StockMovement]:
        """
        Record a stock movement and update product quantity.
        Atomic operation.
        """
        with get_db_session() as session:
            product = session.get(Product, product_id)
            if not product:
                raise ValueError(f"Product {product_id} not found")

            if product.is_service:
                return None

            # Update Stock
            product.stock_qty += qty_change

            # Create Movement Record
            movement = StockMovement(
                product_id=product_id,
                user_id=user_id,
                qty_change=qty_change,
                balance_after=product.stock_qty,
                reference=reference,
                type=movement_type,
            )
            session.add(movement)
            session.commit()
            session.refresh(movement)
            return movement

    @staticmethod
    def get_history(product_id: int) -> List[StockMovement]:
        with get_db_session() as session:
            stmt = (
                select(StockMovement)
                .where(StockMovement.product_id == product_id)
                .order_by(StockMovement.timestamp.desc())
            )
            return list(session.scalars(stmt).all())

    @staticmethod
    def get_reorder_list() -> List[Product]:
        with get_db_session() as session:
            stmt = select(Product).where(
                Product.is_active.is_(True),
                Product.is_service.is_(False),
                Product.stock_qty <= Product.reorder_point,
            )
            return list(session.scalars(stmt).all())
