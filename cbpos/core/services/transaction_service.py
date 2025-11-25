import uuid
from decimal import Decimal
from datetime import datetime
from cbpos.core.database import Database
from cbpos.core.models import Sale, SaleItem, Product, SuspendedTransaction, Customer, SalePayment, CompositeItem
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.tax_service import TaxService

class TransactionService:
    """
    Service to handle the persistence of sales transactions.
    Ensures Atomicity (All or Nothing).
    """

    @staticmethod
    def process_sale(cart_service: CartService, payments: list, customer_id: int = None) -> bool:
        """
        Process the sale with multiple payments.
        
        Args:
            cart_service: The cart containing items.
            payments: List of dicts [{'method': 'CASH', 'amount': 500}, ...]
            customer_id: Optional Customer ID for credit sales.
        """
        db = Database()
        session = db.SessionLocal()
        
        try:
            # 1. Prepare Data
            totals = cart_service.get_totals()
            total_amount = totals['subtotal']
            
            # Validate Payments
            total_paid = sum(p['amount'] for p in payments)
            if total_paid < total_amount:
                raise ValueError(f"Insufficient payment. Paid: {total_paid}, Due: {total_amount}")

            # Generate Receipt No
            receipt_no = f"REC-{uuid.uuid4().hex[:8].upper()}"
            
            # Get Current User
            current_user = AuthService.get_current_user()
            if not current_user:
                raise ValueError("No user logged in.")
            cashier_id = current_user.id

            # Handle Credit Logic
            for p in payments:
                if p['method'] == 'CREDIT':
                    if not customer_id:
                        raise ValueError("Customer required for Credit sale.")
                    
                    customer = session.query(Customer).with_for_update().get(customer_id)
                    if not customer:
                        raise ValueError("Invalid Customer.")
                    
                    if customer.current_balance + p['amount'] > customer.credit_limit:
                        raise ValueError(f"Credit limit exceeded for {customer.name}.")
                    
                    customer.current_balance += p['amount']

            # 2. Create Sale Header
            tax_info = TaxService.calculate_taxes(total_amount)
            
            # Determine primary method for simple display
            primary_method = payments[0]['method'] if len(payments) == 1 else "SPLIT"

            sale = Sale(
                receipt_no=receipt_no,
                timestamp=datetime.now(),
                total_amount=total_amount,
                tax_vat=tax_info['vat'],
                tax_sscl=tax_info['sscl'],
                net_revenue=tax_info['net'],
                payment_method=primary_method,
                cashier_id=cashier_id,
                customer_id=customer_id
            )
            session.add(sale)
            session.flush()
            
            # 3. Create Sale Payments
            for p in payments:
                payment = SalePayment(
                    sale_id=sale.id,
                    payment_method=p['method'],
                    amount=p['amount']
                )
                session.add(payment)

                # 4. Process Items & Deduct Stock
            for item in cart_service.items:
                product = item['product']
                qty = item['qty']
                
                sale_item = SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    qty=qty,
                    unit_price=item['unit_price'],
                    subtotal=item['total']
                )
                session.add(sale_item)
                
                # Check for Composite Item
                # We need to query if this product is a parent in composite_items
                # Since we don't have a direct relationship on Product for 'children' in the snippet provided,
                # we query CompositeItem table.
                # Ideally Product should have `composite_children` relationship. 
                # Let's check the model definition in `models/__init__.py`.
                # It seems `CompositeItem` has `parent` and `child` relationships but `Product` doesn't have `children`.
                # So we query manually.
                
                composite_children = session.query(CompositeItem).filter(CompositeItem.parent_product_id == product.id).all()
                
                if composite_children:
                    # Deduct from children
                    for comp in composite_children:
                        child_product = session.query(Product).with_for_update().get(comp.child_product_id)
                        if child_product:
                            deduction = comp.qty * qty
                            child_product.stock_qty -= deduction
                else:
                    # Deduct from product itself
                    db_product = session.query(Product).with_for_update().get(product.id)
                    if db_product:
                        db_product.stock_qty -= qty

            # 5. Commit
            session.commit()
            
            # 6. Hardware Output
            from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
            from cbpos.core.services.receipt_builder import ReceiptBuilder
            
            worker = PrintWorker()
            receipt_text = ReceiptBuilder.build_receipt(sale)
            worker.add_job('print_receipt', receipt_text)
            worker.add_job('kick_drawer')
            
            return True
            
        except Exception as e:
            print(f"Transaction Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def hold_bill(cart_service: CartService, note: str = None) -> bool:
        """Serialize cart items and save to SuspendedTransaction."""
        import json
        db = Database()
        session = db.SessionLocal()
        try:
            # Serialize cart items
            items_data = []
            for item in cart_service.items:
                items_data.append({
                    'barcode': item['product'].barcode,
                    'qty': str(item['qty'])
                })
            
            json_data = json.dumps(items_data)
            
            suspended = SuspendedTransaction(data=json_data, note=note)
            session.add(suspended)
            session.commit()
            return True
        except Exception as e:
            print(f"Hold Bill Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def get_held_bills() -> list:
        """Return a list of all suspended transactions."""
        db = Database()
        session = db.SessionLocal()
        try:
            suspended = session.query(SuspendedTransaction).order_by(SuspendedTransaction.timestamp.desc()).all()
            # Detach objects
            for s in suspended:
                session.expunge(s)
            return suspended
        finally:
            session.close()

    @staticmethod
    def recall_bill(suspended_id: int, cart_service: CartService) -> bool:
        """Restore cart from SuspendedTransaction and delete the record."""
        import json
        from cbpos.core.services.product_service import ProductService
        
        db = Database()
        session = db.SessionLocal()
        try:
            suspended = session.query(SuspendedTransaction).get(suspended_id)
            if not suspended:
                return False
            
            items_data = json.loads(suspended.data)
            cart_service.clear()
            
            for item in items_data:
                product = ProductService.get_by_barcode(item['barcode'])
                if product:
                    cart_service.add_item(product, Decimal(item['qty']))
            
            session.delete(suspended)
            session.commit()
            return True
        except Exception as e:
            print(f"Recall Bill Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def void_sale(sale_id: int, user_id: int, reason: str) -> bool:
        """
        Mark sale as VOID and reverse stock deduction.
        Security: Caller must ensure user has permission.
        """
        db = Database()
        session = db.SessionLocal()
        try:
            sale = session.query(Sale).get(sale_id)
            if not sale:
                return False
            
            if sale.status == "VOID":
                return False # Already voided
            
            sale.status = "VOID"
            
            # Reverse Stock
            for item in sale.items:
                product = session.query(Product).with_for_update().get(item.product_id)
                if product:
                    product.stock_qty += item.qty
            
            # Log reason (Ideally in an Audit Log, but printing for now)
            print(f"VOID Sale {sale.receipt_no} by User {user_id}: {reason}")
            
            session.commit()
            return True
        except Exception as e:
            print(f"Void Sale Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()
