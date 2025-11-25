from decimal import Decimal
from cbpos.core.database import Database
from cbpos.core.models import Product, InventoryLog
from cbpos.core.services.auth_service import AuthService

class InventoryService:
    """
    Service to handle inventory operations.
    """

    @staticmethod
    def adjust_stock(product_id: int, qty_change: Decimal, reason: str) -> bool:
        """
        Adjust stock quantity for a product and log the change.
        
        Args:
            product_id (int): ID of the product.
            qty_change (Decimal): Amount to change (positive or negative).
            reason (str): Reason for the adjustment.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        db = Database()
        session = db.SessionLocal()
        try:
            current_user = AuthService.get_current_user()
            if not current_user:
                raise ValueError("No user logged in.")

            product = session.query(Product).with_for_update().get(product_id)
            if not product:
                raise ValueError("Product not found.")

            product.stock_qty += qty_change
            
            log = InventoryLog(
                product_id=product.id,
                qty_change=qty_change,
                new_qty=product.stock_qty,
                reason=reason,
                user_id=current_user.id
            )
            session.add(log)
            session.commit()
            return True
        except Exception as e:
            print(f"Stock Adjustment Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def get_low_stock_products(threshold: Decimal = Decimal("10.000")) -> list:
        """
        Get list of products with stock below threshold.
        """
        db = Database()
        with db.get_session() as session:
            products = session.query(Product).filter(Product.stock_qty < threshold).all()
            session.expunge_all()
            return products
