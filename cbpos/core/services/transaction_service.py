import uuid
from decimal import Decimal
from datetime import datetime
from cbpos.core.database import Database
from cbpos.core.models import Sale, SaleItem, Product
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.tax_service import TaxService

class TransactionService:
    """
    Service to handle the persistence of sales transactions.
    Ensures Atomicity (All or Nothing).
    """

    @staticmethod
    def process_sale(cart_service: CartService, payment_method: str, tendered: Decimal) -> bool:
        """
        Process the sale:
        1. Calculate Taxes
        2. Create Sale Header
        3. Create Sale Items
        4. Deduct Stock
        5. Commit Transaction
        """
        db = Database()
        session = db.SessionLocal()
        
        try:
            # 1. Prepare Data
            totals = cart_service.get_totals()
            total_amount = totals['subtotal']
            
            # Generate Receipt No (Simple UUID for now, or Sequence)
            receipt_no = f"REC-{uuid.uuid4().hex[:8].upper()}"
            
            # Get Current User
            current_user = AuthService.get_current_user()
            if not current_user:
                raise ValueError("No user logged in.")
            
            # Re-attach user to this session if needed, or just use ID
            cashier_id = current_user.id

            # 2. Create Sale Header
            # Calculate Taxes
            tax_info = TaxService.calculate_taxes(total_amount)
            
            sale = Sale(
                receipt_no=receipt_no,
                timestamp=datetime.now(),
                total_amount=total_amount,
                tax_vat=tax_info['vat'],
                tax_sscl=tax_info['sscl'],
                net_revenue=tax_info['net'],
                payment_method=payment_method,
                cashier_id=cashier_id
            )
            session.add(sale)
            session.flush() # Flush to get sale.id
            
            # 3. Process Items
            for item in cart_service.items:
                product = item['product']
                qty = item['qty']
                unit_price = item['unit_price']
                subtotal = item['total']
                
                # Create Sale Item
                sale_item = SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    qty=qty,
                    unit_price=unit_price,
                    subtotal=subtotal
                )
                session.add(sale_item)
                
                # 4. Deduct Stock
                # We need to fetch the product in THIS session to lock/update it
                db_product = session.query(Product).with_for_update().get(product.id)
                if db_product:
                    db_product.stock_qty -= qty
                    # Optional: Check for negative stock
                    if db_product.stock_qty < 0:
                        print(f"Warning: Negative stock for {db_product.name_en}")
            
            # 5. Commit
            session.commit()
            return True
            
        except Exception as e:
            print(f"Transaction Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()
