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
        Atomic operation with negative stock validation.
        """
        with get_db_session() as session:
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
                reference=reference,
                type=movement_type,
            )
            session.add(movement)
            session.commit()
            session.refresh(movement)
            return movement

    @staticmethod
    def get_history(product_id: int) -> List[StockMovement]:
        """Get stock movement history for a product."""
        with get_db_session() as session:
            stmt = (
                select(StockMovement)
                .where(StockMovement.product_id == product_id)
                .order_by(StockMovement.timestamp.desc())
            )
            return list(session.scalars(stmt).all())

    @staticmethod
    def get_reorder_list() -> List[Product]:
        """Get list of products that need reordering."""
        with get_db_session() as session:
            stmt = select(Product).where(
                Product.is_active.is_(True),
                Product.is_service.is_(False),
                Product.stock_qty <= Product.reorder_point,
            )
            return list(session.scalars(stmt).all())
