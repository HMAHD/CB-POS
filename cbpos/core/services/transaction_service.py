import uuid
from decimal import Decimal
from datetime import datetime
from cbpos.core.database import Database
from cbpos.core.models import (
    Sale,
    SaleItem,
    Product,
    SuspendedTransaction,
    Customer,
    SalePayment,
    CompositeItem,
)
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.stock_service import StockService
from cbpos.core.services.receipt_service import ReceiptService
from cbpos.core.services.product_service import ProductService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
import json


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
            total_amount = totals["subtotal"]

            # Validate Payments
            total_paid = sum(p["amount"] for p in payments)
            if total_paid < total_amount:
                raise ValueError(f"Insufficient payment. Paid: {total_paid}, Due: {total_amount}")

            # Negative Stock Check

            if not ConfigService.get("allow_negative_stock"):
                # 1. Collect all Product IDs (Parents)
                cart_items = cart_service.items
                parent_ids = [item["product"].id for item in cart_items]

                # 2. Fetch Composite Definitions for these parents
                composites = session.query(CompositeItem).filter(CompositeItem.parent_product_id.in_(parent_ids)).all()

                # 3. Collect Child IDs from Composites
                child_ids = [c.child_product_id for c in composites]

                # 4. Fetch ALL involved Products (Parents + Children) in one query
                all_product_ids = set(parent_ids) | set(child_ids)
                all_products = (
                    session.query(Product)
                    .filter(Product.id.in_(all_product_ids))
                    .with_for_update()  # Lock rows for stock check
                    .all()
                )
                product_map = {p.id: p for p in all_products}

                # 5. Group Composites by Parent
                composite_map = {}
                for comp in composites:
                    composite_map.setdefault(comp.parent_product_id, []).append(comp)

                # 6. Perform Stock Check in Memory
                for item in cart_items:
                    product_id = item["product"].id
                    qty_needed = item["qty"]

                    # Get fresh product from map
                    product = product_map.get(product_id)
                    if not product:
                        raise ValueError(f"Product {product_id} missing from database.")

                    comps = composite_map.get(product_id, [])

                    if comps:
                        # Check children stock
                        for comp in comps:
                            child_product = product_map.get(comp.child_product_id)
                            if not child_product:
                                raise ValueError(f"Component product {comp.child_product_id} missing.")

                            required_qty = comp.qty * qty_needed
                            if child_product.stock_qty < required_qty:
                                raise ValueError(
                                    f"Insufficient stock for component '{child_product.name_en}' "
                                    f"(in {product.name_en}). Available: {child_product.stock_qty}, "
                                    f"Required: {required_qty}"
                                )
                    else:
                        # Check direct stock
                        if product.stock_qty < qty_needed:
                            raise ValueError(
                                f"Insufficient stock for '{product.name_en}'. "
                                f"Available: {product.stock_qty}, Required: {qty_needed}"
                            )

            # Generate Receipt No
            receipt_no = f"REC-{uuid.uuid4().hex[:8].upper()}"

            # Get Current User
            current_user = AuthService.get_current_user()
            if not current_user:
                raise ValueError("No user logged in.")
            cashier_id = current_user.id

            # Handle Credit Logic
            for p in payments:
                if p["method"] == "CREDIT":
                    if not customer_id:
                        raise ValueError("Customer required for Credit sale.")

                    customer = session.query(Customer).with_for_update().get(customer_id)
                    if not customer:
                        raise ValueError("Invalid Customer.")

                    if customer.current_balance + p["amount"] > customer.credit_limit:
                        raise ValueError(f"Credit limit exceeded for {customer.name}.")

                    customer.current_balance += p["amount"]

            # 2. Create Sale Header
            tax_info = TaxService.calculate_taxes(total_amount)

            # Determine primary method for simple display
            primary_method = payments[0]["method"] if len(payments) == 1 else "SPLIT"

            sale = Sale(
                document_number=receipt_no,
                date=datetime.now(),
                total_amount=total_amount,
                tax_vat=tax_info["vat"],
                tax_sscl=tax_info["sscl"],
                net_revenue=tax_info["net"],
                payment_method=primary_method,
                user_id=cashier_id,
                customer_id=customer_id,
            )
            session.add(sale)
            session.flush()

            # 3. Create Sale Payments
            for p in payments:
                payment = SalePayment(sale_id=sale.id, payment_method=p["method"], amount=p["amount"])
                session.add(payment)

                # 4. Process Items & Deduct Stock

            for item in cart_service.items:
                product = item["product"]
                qty = item["qty"]

                sale_item = SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    qty=qty,
                    unit_price=item["unit_price"],
                    original_price=item["original_price"],
                    subtotal=item["total"],
                )
                session.add(sale_item)

                # Check for Composite Item
                composite_children = (
                    session.query(CompositeItem).filter(CompositeItem.parent_product_id == product.id).all()
                )

                if composite_children:
                    # Deduct from children
                    for comp in composite_children:
                        deduction = comp.qty * qty
                        StockService.record_movement(
                            product_id=comp.child_product_id,
                            qty_change=-deduction,
                            movement_type="SALE",
                            document_id=sale.id,
                            user_id=cashier_id,
                            session=session,
                        )
                else:
                    # Deduct from product itself
                    StockService.record_movement(
                        product_id=product.id,
                        qty_change=-qty,
                        movement_type="SALE",
                        document_id=sale.id,
                        user_id=cashier_id,
                        session=session,
                    )

            # 5. Commit
            session.commit()

            # 6. Hardware Output
            worker = PrintWorker()

            # Check language for Unicode support
            settings = ConfigService.get_all()
            language = settings.get("language", "en")

            if language == "en":
                # Text Mode
                receipt_text = ReceiptService.build_receipt_text(sale)
                worker.add_job("print_receipt", receipt_text)
            else:
                # Image Mode (Unicode)
                receipt_image = ReceiptService.build_receipt_image(sale)
                worker.add_job("print_image", receipt_image)

            worker.add_job("kick_drawer")

            return True

        except ValueError as e:
            # Handle insufficient stock or validation errors
            error_msg = str(e)
            print("Transaction Error: {0}".format(error_msg))
            session.rollback()
            raise  # Re-raise to allow UI to handle
        except Exception as e:
            print("Transaction Failed: {0}".format(e))
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def hold_bill(cart_service: CartService, note: str = None) -> bool:
        """Serialize cart items and save to SuspendedTransaction."""
        db = Database()
        session = db.SessionLocal()
        try:
            # Serialize cart items
            items_data = []
            for item in cart_service.items:
                items_data.append({"barcode": item["product"].barcode, "qty": str(item["qty"])})

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

        db = Database()
        session = db.SessionLocal()
        try:
            suspended = session.query(SuspendedTransaction).get(suspended_id)
            if not suspended:
                return False

            items_data = json.loads(suspended.data)
            cart_service.clear()

            for item in items_data:
                product = ProductService.get_by_barcode(item["barcode"])
                if product:
                    cart_service.add_item(product, Decimal(item["qty"]))

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
                return False  # Already voided

            sale.status = "VOID"

            # Reverse Stock
            for item in sale.items:
                product = session.query(Product).with_for_update().get(item.product_id)
                if product:
                    product.stock_qty += item.qty

            # Log reason (Ideally in an Audit Log, but printing for now)
            print(f"VOID Sale {sale.document_number} by User {user_id}: {reason}")

            session.commit()
            return True
        except Exception as e:
            print(f"Void Sale Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def process_refund(original_sale_id: int, refund_reason: str, user_id: int) -> bool:
        """
        Process a full refund for a previous sale.
        Creates a negative transaction and restores stock.

        Args:
            original_sale_id: ID of the original sale to refund
            refund_reason: Reason for the refund
            user_id: Current user ID processing the refund

        Returns:
            bool: True if successful
        """
        db = Database()
        session = db.SessionLocal()

        try:
            # 1. Validate original sale
            original_sale = session.query(Sale).get(original_sale_id)
            if not original_sale:
                raise ValueError(f"Sale ID {original_sale_id} not found.")

            if original_sale.status == "VOID":
                raise ValueError("Cannot refund a voided sale.")

            if original_sale.payment_method == "REFUND":
                raise ValueError("Cannot refund a refund transaction.")

            # Check if already refunded
            existing_refund = session.query(Sale).filter(Sale.refund_of_sale_id == original_sale_id).first()
            if existing_refund:
                raise ValueError(f"Sale already refunded (Refund: {existing_refund.document_number})")

            # 2. Create refund transaction (negative values)
            refund_receipt_no = f"REF-{uuid.uuid4().hex[:8].upper()}"

            # Calculate negative taxes
            refund_amount = -original_sale.total_amount
            tax_info = TaxService.calculate_taxes(refund_amount)

            refund_sale = Sale(
                document_number=refund_receipt_no,
                date=datetime.now(),
                total_amount=refund_amount,
                tax_vat=tax_info["vat"],
                tax_sscl=tax_info["sscl"],
                net_revenue=tax_info["net"],
                payment_method="REFUND",
                status="COMPLETED",
                user_id=user_id,
                customer_id=original_sale.customer_id,
                refund_of_sale_id=original_sale_id,
            )
            session.add(refund_sale)
            session.flush()

            # 3. Create refund line items (negative quantities)
            for original_item in original_sale.items:
                refund_item = SaleItem(
                    sale_id=refund_sale.id,
                    product_id=original_item.product_id,
                    qty=-original_item.qty,
                    unit_price=original_item.unit_price,
                    subtotal=-original_item.subtotal,
                )
                session.add(refund_item)

                # 4. RESTORE stock (increase)
                product = session.query(Product).with_for_update().get(original_item.product_id)
                if product:
                    # Check if composite
                    composite_children = (
                        session.query(CompositeItem).filter(CompositeItem.parent_product_id == product.id).all()
                    )

                    if composite_children:
                        # Restore child product stock
                        for comp in composite_children:
                            child_product = session.query(Product).with_for_update().get(comp.child_product_id)
                            if child_product:
                                restoration = comp.qty * original_item.qty
                                child_product.stock_qty += restoration
                    else:
                        # Restore product stock directly
                        product.stock_qty += original_item.qty

            # 5. Create refund payment record
            refund_payment = SalePayment(
                sale_id=refund_sale.id,
                payment_method="REFUND",
                amount=refund_amount,
            )
            session.add(refund_payment)

            # 6. Log the refund
            print(
                f"REFUND: {original_sale.document_number} -> " f"{refund_receipt_no} by User {user_id}: {refund_reason}"
            )

            # 7. Commit
            session.commit()

            # 8. Print refund voucher
            worker = PrintWorker()
            settings = ConfigService.get_all()
            language = settings.get("language", "en")

            if language == "en":
                receipt_text = ReceiptService.build_receipt_text(refund_sale)
                worker.add_job("print_receipt", receipt_text)
            else:
                receipt_image = ReceiptService.build_receipt_image(refund_sale)
                worker.add_job("print_image", receipt_image)

            return True

        except Exception as e:
            print(f"Refund Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def lock_order(sale_id: int) -> bool:
        """
        Lock an order to prevent further edits.
        Useful for pre-payments or finalized but unpaid orders.
        """
        db = Database()
        session = db.SessionLocal()
        try:
            sale = session.query(Sale).get(sale_id)
            if not sale:
                return False

            sale.status = "LOCKED"
            session.commit()
            return True
        except Exception as e:
            print(f"Lock Order Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def transfer_order(sale_id: int, target_user_id: int) -> bool:
        """
        Transfer ownership of an order to another user.
        """
        from cbpos.core.models import User, AuditLog

        db = Database()
        session = db.SessionLocal()
        try:
            sale = session.query(Sale).get(sale_id)
            target_user = session.query(User).get(target_user_id)

            if not sale or not target_user:
                return False

            old_user_id = sale.user_id
            sale.user_id = target_user_id

            # Audit Log
            log = AuditLog(
                user_id=old_user_id,  # Logged by original owner (or current user)
                action="TRANSFER_ORDER",
                event_type="TRANSACTION",
                details=f"Order {sale.document_number} transferred to {target_user.username} (ID: {target_user_id})",
            )
            session.add(log)

            session.commit()
            return True
        except Exception as e:
            print(f"Transfer Order Failed: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def get_held_bill_count() -> int:
        """Return the number of currently held bills."""
        db = Database()
        with db.get_session() as session:
            return session.query(SuspendedTransaction).count()
