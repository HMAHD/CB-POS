import uuid
import logging
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import joinedload
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
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.stock_service import StockService
from cbpos.core.services.receipt_service import ReceiptService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.utils.formatters import escape_like
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
import json

logger = logging.getLogger(__name__)


class TransactionService:
    """
    Service to handle the persistence of sales transactions.
    Ensures Atomicity (All or Nothing).
    """

    @staticmethod
    def process_sale(cart_service: CartService, payments: list, customer_id: int = None) -> Sale | None:
        """
        Process the sale with multiple payments.

        Args:
            cart_service: The cart containing items.
            payments: List of dicts [{'method': 'CASH', 'amount': 500}, ...]
            customer_id: Optional Customer ID for credit sales.

        Returns:
            Sale object on success, None on failure.

        Raises:
            ValueError: If validation fails or insufficient stock.
        """
        try:
            return TransactionService._execute_sale(cart_service, payments, customer_id)
        except ValueError:
            raise
        except Exception as e:
            logger.error("Failed to process sale: %s", e)
            return None

    @staticmethod
    def _execute_sale(cart_service: CartService, payments: list, customer_id: int = None) -> Sale:
        """Internal method that executes the sale transaction."""
        db = Database()
        with db.get_session() as session:
            # 1. Prepare Data
            totals = cart_service.get_totals()
            total_amount = totals["final_total"]

            # Validate Payments
            total_paid = sum(p["amount"] for p in payments)
            if total_paid < total_amount:
                raise ValueError(f"Insufficient payment. Paid: {total_paid}, Due: {total_amount}")

            # Pre-fetch composite items for all cart products (avoids N+1 queries later)
            cart_items = cart_service.items
            parent_ids = [item["product"].id for item in cart_items]
            composites = session.query(CompositeItem).filter(CompositeItem.parent_product_id.in_(parent_ids)).all()

            # Group composites by parent for O(1) lookup
            composite_map = {}
            for comp in composites:
                composite_map.setdefault(comp.parent_product_id, []).append(comp)

            # Negative Stock Check
            if not ConfigService.get("allow_negative_stock"):
                # Collect Child IDs from Composites
                child_ids = [c.child_product_id for c in composites]

                # Fetch ALL involved Products (Parents + Children) in one query
                all_product_ids = set(parent_ids) | set(child_ids)
                all_products = (
                    session.query(Product)
                    .filter(Product.id.in_(all_product_ids))
                    .with_for_update()  # Lock rows for stock check
                    .all()
                )
                product_map = {p.id: p for p in all_products}

                # Perform Stock Check in Memory
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
            from cbpos.core.constants.status import PaymentMethodType

            credit_amount_for_ledger = None
            credit_customer_balance = None
            for p in payments:
                if p["method"].upper() == PaymentMethodType.CREDIT.upper():
                    if not customer_id:
                        raise ValueError("Customer required for Credit sale.")

                    customer = session.get(Customer, customer_id, with_for_update=True)
                    if not customer:
                        raise ValueError("Invalid Customer.")

                    if customer.current_debt + p["amount"] > customer.credit_limit:
                        raise ValueError(f"Credit limit exceeded for {customer.name}.")

                    customer.current_debt += p["amount"]
                    # Ledger entry will be created after sale is flushed (need sale.id)
                    credit_amount_for_ledger = p["amount"]
                    credit_customer_balance = customer.current_debt

            # 2. Create Sale Header — use tax values from cart totals (single source of truth)
            exempt_amount = totals.get("exempt_amount", Decimal("0"))
            tax_info = {
                "vat": totals["tax_vat"],
                "sscl": totals["tax_sscl"],
                "net": totals["net_revenue"],
            }

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
                terminal_id=ConfigService.get("terminal_id") or "TERM-01",
            )
            # Attach exempt amount for receipt builder (transient, not persisted)
            sale._exempt_amount = exempt_amount
            session.add(sale)
            session.flush()

            # Record credit sale in ledger (if applicable)
            if customer_id and credit_amount_for_ledger is not None:
                CustomerCreditService.record_credit_sale_in_session(
                    session=session,
                    customer_id=customer_id,
                    sale_id=sale.id,
                    amount=credit_amount_for_ledger,
                    doc_number=receipt_no,
                    balance_after=credit_customer_balance,
                    user_id=cashier_id,
                )

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

                # Check for Composite Item (using pre-fetched map)
                composite_children = composite_map.get(product.id, [])

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

            # 5. Eager-load relationships before session closes (prevents DetachedInstanceError)
            if sale.customer_id:
                _ = sale.customer  # Force load while session is open

            # 6. Context manager handles commit

            # 7. Hardware Output (after successful commit)
            worker = PrintWorker()

            # If receipt dialog is enabled, skip auto-print (dialog handles it).
            # Otherwise, print receipt automatically for frictionless flow.
            show_dialog = ConfigService.get("show_receipt_dialog")
            if not show_dialog:
                settings = ConfigService.get_all()
                language = settings.get("language", "en")

                if language == "en":
                    receipt_text = ReceiptService.build_receipt_text(sale)
                    worker.add_job("print_receipt", receipt_text)
                else:
                    receipt_image = ReceiptService.build_receipt_image(sale)
                    worker.add_job("print_image", receipt_image)

            payment_methods = [p.payment_method for p in sale.payments] if sale.payments else []
            worker.add_job("kick_drawer", payment_methods)

            return sale

    @staticmethod
    def hold_bill(cart_service: CartService, note: str = None) -> int | None:
        """Serialize cart items and save to SuspendedTransaction.

        Returns the suspended transaction ID on success, None on failure.
        """
        db = Database()
        try:
            with db.get_session() as session:
                # Serialize cart items
                items_data = []
                for item in cart_service.items:
                    items_data.append({"barcode": item["product"].barcode, "qty": str(item["qty"])})

                json_data = json.dumps(items_data)

                suspended = SuspendedTransaction(data=json_data, note=note)
                session.add(suspended)
                session.flush()
                return suspended.id
        except Exception as e:
            logger.error("Hold Bill Failed: %s", e)
            return None

    @staticmethod
    def get_held_bills() -> list:
        """Return a list of all suspended transactions."""
        db = Database()
        with db.get_session() as session:
            suspended = session.query(SuspendedTransaction).order_by(SuspendedTransaction.timestamp.desc()).all()
            # Detach objects
            for s in suspended:
                session.expunge(s)
            return suspended

    @staticmethod
    def recall_bill(suspended_id: int, cart_service: CartService) -> bool:
        """Restore cart from SuspendedTransaction and delete the record."""
        db = Database()
        try:
            with db.get_session() as session:
                suspended = session.get(SuspendedTransaction, suspended_id)
                if not suspended:
                    return False

                items_data = json.loads(suspended.data)
                cart_service.clear()

                for item in items_data:
                    product = ProductService.get_by_barcode(item["barcode"])
                    if product:
                        cart_service.add_item(product, Decimal(item["qty"]))

                session.delete(suspended)
            return True
        except Exception as e:
            logger.error("Recall Bill Failed: %s", e)
            return False

    @staticmethod
    def void_sale(sale_id: int, user_id: int, reason: str) -> bool:
        """
        Mark sale as VOID and reverse stock deduction.
        Security: Caller must ensure user has permission.
        Uses StockService for proper audit trail and handles composites.
        """
        db = Database()
        try:
            with db.get_session() as session:
                sale = session.get(Sale, sale_id, options=[joinedload(Sale.items)])
                if not sale:
                    return False

                if sale.status == "VOID":
                    return False  # Already voided

                sale.status = "VOID"

                # Pre-fetch composite items for all products in sale
                product_ids = [item.product_id for item in sale.items]
                composites = session.query(CompositeItem).filter(CompositeItem.parent_product_id.in_(product_ids)).all()
                composite_map = {}
                for comp in composites:
                    composite_map.setdefault(comp.parent_product_id, []).append(comp)

                # Reverse Stock via StockService
                for item in sale.items:
                    composite_children = composite_map.get(item.product_id, [])

                    if composite_children:
                        for comp in composite_children:
                            restoration = comp.qty * item.qty
                            StockService.record_movement(
                                product_id=comp.child_product_id,
                                qty_change=restoration,
                                movement_type="VOID",
                                document_id=sale.id,
                                user_id=user_id,
                                session=session,
                            )
                    else:
                        StockService.record_movement(
                            product_id=item.product_id,
                            qty_change=item.qty,
                            movement_type="VOID",
                            document_id=sale.id,
                            user_id=user_id,
                            session=session,
                        )

                logger.info("VOID Sale %s by User %s: %s", sale.document_number, user_id, reason)
            return True
        except Exception as e:
            logger.error("Void Sale Failed: %s", e)
            return False

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
        try:
            with db.get_session() as session:
                # 1. Validate original sale
                original_sale = session.get(Sale, original_sale_id, options=[joinedload(Sale.items)])
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

                # Pre-fetch composite items for all products in sale
                product_ids = [item.product_id for item in original_sale.items]
                composites = session.query(CompositeItem).filter(CompositeItem.parent_product_id.in_(product_ids)).all()
                composite_map = {}
                for comp in composites:
                    composite_map.setdefault(comp.parent_product_id, []).append(comp)

                # 2. Create refund transaction (negative values)
                refund_receipt_no = f"REF-{uuid.uuid4().hex[:8].upper()}"

                # Mirror original sale's tax values (negated) to preserve
                # correct tax breakdown, especially for sales with exempt items.
                # Recalculating from the total would lose exempt-item granularity.
                refund_amount = -original_sale.total_amount
                refund_vat = -(original_sale.tax_vat or Decimal("0"))
                refund_sscl = -(original_sale.tax_sscl or Decimal("0"))
                refund_net = -(original_sale.net_revenue or Decimal("0"))

                refund_sale = Sale(
                    document_number=refund_receipt_no,
                    date=datetime.now(),
                    total_amount=refund_amount,
                    tax_vat=refund_vat,
                    tax_sscl=refund_sscl,
                    net_revenue=refund_net,
                    payment_method="REFUND",
                    status="COMPLETED",
                    user_id=user_id,
                    customer_id=original_sale.customer_id,
                    refund_of_sale_id=original_sale_id,
                    terminal_id=ConfigService.get("terminal_id") or "TERM-01",
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
                        original_price=original_item.original_price or original_item.unit_price,
                        subtotal=-original_item.subtotal,
                    )
                    session.add(refund_item)

                    # 4. RESTORE stock (increase)
                    product = session.get(Product, original_item.product_id, with_for_update=True)
                    if product:
                        composite_children = composite_map.get(product.id, [])

                        if composite_children:
                            # Restore child product stock
                            for comp in composite_children:
                                child_product = session.get(Product, comp.child_product_id, with_for_update=True)
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

                logger.info(
                    "REFUND: %s -> %s by User %s: %s",
                    original_sale.document_number,
                    refund_receipt_no,
                    user_id,
                    refund_reason,
                )

                # 6. Print refund voucher (after commit via context manager)
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
            logger.error("Refund Failed: %s", e)
            return False

    @staticmethod
    def lock_order(sale_id: int) -> bool:
        """
        Lock an order to prevent further edits.
        Useful for pre-payments or finalized but unpaid orders.
        """
        db = Database()
        try:
            with db.get_session() as session:
                sale = session.get(Sale, sale_id)
                if not sale:
                    return False

                sale.status = "LOCKED"
            return True
        except Exception as e:
            logger.error("Lock Order Failed: %s", e)
            return False

    @staticmethod
    def transfer_order(sale_id: int, target_user_id: int) -> bool:
        """
        Transfer ownership of an order to another user.
        """
        from cbpos.core.models import User, AuditLog

        db = Database()
        try:
            with db.get_session() as session:
                sale = session.get(Sale, sale_id)
                target_user = session.get(User, target_user_id)

                if not sale or not target_user:
                    return False

                old_user_id = sale.user_id
                sale.user_id = target_user_id

                # Audit Log
                log = AuditLog(
                    user_id=old_user_id,
                    action="TRANSFER_ORDER",
                    event_type="TRANSACTION",
                    details=f"Order {sale.document_number} transferred to {target_user.username}",
                )
                session.add(log)
            return True
        except Exception as e:
            logger.error("Transfer Order Failed: %s", e)
            return False

    @staticmethod
    def get_held_bill_count() -> int:
        """Return the number of currently held bills."""
        db = Database()
        with db.get_session() as session:
            return session.query(SuspendedTransaction).count()

    @staticmethod
    def get_last_sale() -> Sale:
        """Return the most recent sale, detached from session."""
        db = Database()
        with db.get_session() as session:
            sale = (
                session.query(Sale)
                .options(
                    joinedload(Sale.items).joinedload(SaleItem.product),
                    joinedload(Sale.customer),
                    joinedload(Sale.payments),
                )
                .order_by(Sale.id.desc())
                .first()
            )
            if sale:
                session.expunge(sale)
            return sale

    @staticmethod
    def get_latest_suspended() -> SuspendedTransaction:
        """Return the most recent suspended transaction, detached from session."""
        db = Database()
        with db.get_session() as session:
            suspended = session.query(SuspendedTransaction).order_by(SuspendedTransaction.timestamp.desc()).first()
            if suspended:
                session.expunge(suspended)
            return suspended

    @staticmethod
    def get_sales_history(
        from_date: datetime,
        to_date: datetime,
        search_term: str = None,
        limit: int = 500,
    ) -> list:
        """
        Fetch sales within a date range with optional search filter.

        Args:
            from_date: Start datetime
            to_date: End datetime
            search_term: Optional receipt# or customer name filter
            limit: Maximum number of results (default 500)

        Returns:
            List of detached Sale objects with eager-loaded relationships
        """
        db = Database()
        with db.get_session() as session:
            query = session.query(Sale).filter(
                Sale.date >= from_date,
                Sale.date <= to_date,
            )

            if search_term:
                query = query.filter(
                    (Sale.document_number.like(f"%{escape_like(search_term)}%")) | (Sale.customer.has(name=search_term))
                )

            from cbpos.core.models import SaleItem

            sales = (
                query.options(
                    joinedload(Sale.user),
                    joinedload(Sale.customer),
                    joinedload(Sale.items).joinedload(SaleItem.product),
                )
                .order_by(Sale.date.desc())
                .limit(limit)
                .all()
            )

            # Detach from session
            for sale in sales:
                session.expunge(sale)

            return sales

    @staticmethod
    def get_sale_details(sale_id: int) -> Sale:
        """
        Fetch a single sale with all relationships loaded.

        Args:
            sale_id: Sale ID to fetch

        Returns:
            Detached Sale object or None
        """
        db = Database()
        with db.get_session() as session:
            sale = session.get(
                Sale,
                sale_id,
                options=[
                    joinedload(Sale.items).joinedload(SaleItem.product),
                    joinedload(Sale.user),
                    joinedload(Sale.customer),
                ],
            )
            if sale:
                session.expunge(sale)
            return sale
