import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.status import DocumentStatus, PaymentMethodType, Precision, ShiftStatus
from cbpos.core.database import Database
from cbpos.core.interfaces.transaction_peripherals import (
    NullPeripherals,
    RefundCompleted,
    SaleCompleted,
    TransactionPeripherals,
)
from cbpos.core.models import (
    AuditLog,
    CompositeItem,
    Customer,
    Product,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    User,
    VoidReason,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.document_service import DocumentService
from cbpos.core.services.loyalty_service import LoyaltyService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.refund_breakdown import ZERO_MONEY, RefundBreakdown, refund_cash_back
from cbpos.core.services.stock_service import StockService

logger = logging.getLogger(__name__)


class TransactionService:
    """
    Service to handle the persistence of sales transactions.
    Ensures Atomicity (All or Nothing).

    For sale queries, see SaleQueryService.
    For suspended/held bills, see SuspendedTransactionService.

    Hardware (receipt, invoice, cash drawer, refund voucher) is reached only through the
    installed ``TransactionPeripherals`` adapter -- see ``use_peripherals``.
    """

    _peripherals: TransactionPeripherals = NullPeripherals()

    @staticmethod
    def use_peripherals(peripherals: TransactionPeripherals) -> TransactionPeripherals:
        """Install the hardware adapter every committed transaction is reported to.

        Called once at app startup (``main()``) with the production adapter;
        until then the headless ``NullPeripherals`` default does nothing.

        Args:
            peripherals: The adapter to install.

        Returns:
            TransactionPeripherals: The adapter it replaces (so a test can put it back).
        """
        previous = TransactionService._peripherals
        TransactionService._peripherals = peripherals
        return previous

    @staticmethod
    def process_sale(
        cart_service: CartService,
        payments: list,
        customer_id: int = None,
        peripherals: TransactionPeripherals | None = None,
        loyalty_points_redeemed: int = 0,
    ) -> Sale | None:
        """
        Process the sale with multiple payments.

        Args:
            cart_service: The cart containing items.
            payments: List of dicts [{'method': 'CASH', 'amount': 500}, ...]
            customer_id: Optional Customer ID for credit sales.
            peripherals: Hardware adapter for this sale only; defaults to the
                installed one (``use_peripherals``).
            loyalty_points_redeemed: Optional loyalty points redeemed as discount.

        Returns:
            Sale object on success, None on failure.

        Raises:
            ValueError: If validation fails or insufficient stock.
        """
        try:
            return TransactionService._execute_sale(
                cart_service,
                payments,
                customer_id,
                peripherals or TransactionService._peripherals,
                loyalty_points_redeemed=loyalty_points_redeemed,
            )
        except ValueError:
            raise
        except Exception as e:
            logger.error("Failed to process sale: %s", e)
            return None

    @staticmethod
    def _fetch_composite_map(session: Session, product_ids: list) -> dict:
        """Pre-fetch composite items for a list of product IDs.

        Returns a dict mapping parent_product_id to list of CompositeItem objects.
        """
        composites = session.query(CompositeItem).filter(CompositeItem.parent_product_id.in_(product_ids)).all()
        composite_map: dict[int, list] = {}
        for comp in composites:
            composite_map.setdefault(comp.parent_product_id, []).append(comp)
        return composite_map

    @staticmethod
    def _check_stock(
        session: Session, cart_items: list[dict[str, Any]], composite_map: dict[int, list[CompositeItem]]
    ) -> None:
        """Make sure every cart line can be taken from stock, unless negative stock is allowed.

        Locks the products involved (parents and components) for the rest of
        the transaction, then checks each line in memory: a composite against
        each component's bill-of-materials qty, any other product against its
        own stock.

        Args:
            session: The open session the sale is being written in.
            cart_items: ``CartService.items`` -- dicts with ``product`` and ``qty``.
            composite_map: ``_fetch_composite_map`` result for the cart's products.

        Raises:
            ValueError: If a product or component is missing, or stock is short.
        """
        if ConfigService.get("allow_negative_stock"):
            return

        parent_ids = [item["product"].id for item in cart_items]
        child_ids = [c.child_product_id for comps in composite_map.values() for c in comps]

        # Fetch ALL involved Products (Parents + Children) in one query
        all_products = (
            session.query(Product)
            .filter(Product.id.in_(set(parent_ids) | set(child_ids)))
            .with_for_update()  # Lock rows for stock check
            .all()
        )
        product_map = {p.id: p for p in all_products}

        for item in cart_items:
            product_id = item["product"].id
            qty_needed = item["qty"]

            product = product_map.get(product_id)
            if not product:
                raise ValueError(f"Product {product_id} missing from database.")

            comps = composite_map.get(product_id, [])
            if not comps:
                if product.stock_qty < qty_needed:
                    raise ValueError(
                        f"Insufficient stock for '{product.name_en}'. "
                        f"Available: {product.stock_qty}, Required: {qty_needed}"
                    )
                continue

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

    @staticmethod
    def _charge_credit(
        session: Session, payments: list[dict[str, Any]], customer_id: int | None
    ) -> tuple[Decimal, Decimal] | None:
        """Put the CREDIT part of the payments on the customer's book (debt only, no ledger row yet).

        Locks the customer row and checks the credit limit before each charge.
        The ledger row needs the sale's id, so it is written afterwards by
        ``_record_credit_charge``.

        Args:
            session: The open session the sale is being written in.
            payments: ``[{"method", "amount"}, ...]`` as passed to ``process_sale``.
            customer_id: The sale's customer, if any.

        Returns:
            ``(amount, balance_after)`` of the (last) CREDIT payment, or None if
            nothing was paid on credit.

        Raises:
            ValueError: If there is no customer, it doesn't exist, or the
                charge would go over the credit limit.
        """
        from cbpos.core.constants.status import PaymentMethodType

        charge = None
        for p in payments:
            if p["method"].upper() != PaymentMethodType.CREDIT.upper():
                continue

            if not customer_id:
                raise ValueError("Customer required for Credit sale.")

            customer = session.get(Customer, customer_id, with_for_update=True)
            if not customer:
                raise ValueError("Invalid Customer.")

            if customer.current_debt + p["amount"] > customer.credit_limit:
                raise ValueError(f"Credit limit exceeded for {customer.name}.")

            customer.current_debt += p["amount"]
            charge = (p["amount"], customer.current_debt)
        return charge

    @staticmethod
    def _record_credit_charge(session: Session, sale: Sale, charge: tuple[Decimal, Decimal] | None) -> None:
        """Write the customer ledger row for a ``_charge_credit`` charge, once ``sale`` has its id and number.

        Args:
            session: The open session the sale is being written in.
            sale: The flushed sale (id, document_number, customer and cashier set).
            charge: ``_charge_credit``'s ``(amount, balance_after)``, or None.
        """
        if not sale.customer_id or charge is None:
            return

        amount, balance_after = charge
        CustomerCreditService.record_credit_sale_in_session(
            session=session,
            customer_id=sale.customer_id,
            sale_id=sale.id,
            amount=amount,
            doc_number=sale.document_number,
            balance_after=balance_after,
            user_id=sale.user_id,
        )

    @staticmethod
    def _move_stock(
        session: Session,
        composite_map: dict[int, list[CompositeItem]],
        product_id: int,
        qty_change: Decimal,
        movement_type: str,
        document_id: int,
        user_id: int,
    ) -> None:
        """Record one line's stock movement, exploding a composite into its components.

        A composite (bundle) holds no stock of its own: each component moves by
        its bill-of-materials qty times ``qty_change``. Any other product moves
        by ``qty_change`` itself.

        Args:
            session: The open session the document is being written in.
            composite_map: ``_fetch_composite_map`` result for the document's products.
            product_id: The line's product.
            qty_change: Signed change for one line (negative takes stock out).
            movement_type: StockMovement type -- "SALE", "VOID" or "RETURN".
            document_id: The sale/refund/voided document the movement belongs to.
            user_id: User the movement is recorded against.
        """
        components = composite_map.get(product_id, [])
        if not components:
            StockService.record_movement(
                product_id=product_id,
                qty_change=qty_change,
                movement_type=movement_type,
                document_id=document_id,
                user_id=user_id,
                session=session,
            )
            return

        for comp in components:
            StockService.record_movement(
                product_id=comp.child_product_id,
                qty_change=comp.qty * qty_change,
                movement_type=movement_type,
                document_id=document_id,
                user_id=user_id,
                session=session,
            )

    @staticmethod
    def _insert_numbered(session: Session, sale: Sale, doc_type: str) -> None:
        """Give ``sale`` the next ``doc_type`` number and flush it, in ``session``'s transaction.

        The number is read and inserted in the same transaction as the rest
        of the sale, so a failed sale leaves no gap and reserves nothing.

        Standalone (SQLite) has a single writer -- one app instance, and the
        sync server only writes terminal-prefixed numbers -- so a plain flush
        is enough. A SAVEPOINT must not be used there: pysqlite only opens
        its transaction at the first INSERT, so the SAVEPOINT becomes the
        outermost transaction and releasing it commits the sale header even
        if the rest of the sale later rolls back.

        Network mode (PostgreSQL) shares one database between tills: another
        till can commit the same number between our read and our insert.
        The unique ``document_number`` index rejects ours; only the SAVEPOINT
        around the insert is rolled back and a fresh number is tried, keeping
        the stock/credit work already done in this transaction.

        Args:
            session: The open session the sale is being written in.
            sale: The new, not yet added Sale.
            doc_type: "SALE" or "RETURN".

        Raises:
            IntegrityError: If no free number is found after a few tries.
        """
        if Database()._db_mode != "network":
            sale.document_number = DocumentService.generate_number(doc_type, session=session)
            session.add(sale)
            session.flush()
            return

        session.flush()  # keep earlier pending changes out of the savepoint
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            sale.document_number = DocumentService.generate_number(doc_type, session=session)
            try:
                with session.begin_nested():
                    session.add(sale)  # flushed when the savepoint closes
                return
            except IntegrityError:
                if attempt == max_attempts:
                    raise
                logger.warning("%s number %s already taken, retrying", doc_type, sale.document_number)

    @staticmethod
    def _new_sale(
        totals: dict[str, Any],
        payments: list[dict[str, Any]],
        cashier_id: int,
        customer_id: int | None,
        shift_id: int | None = None,
    ) -> Sale:
        """Build the (not yet added) sale header from the cart totals.

        Tax values come straight from the cart totals (single source of
        truth). The exempt amount rides along on ``sale._exempt_amount`` for
        the receipt builder -- transient, not persisted.

        Args:
            totals: ``CartService.get_totals()``.
            payments: ``[{"method", "amount"}, ...]`` -- one method is shown as is, several as "SPLIT".
            cashier_id: The signed-in cashier.
            customer_id: The sale's customer, if any.
            shift_id: The cashier's current open shift on this terminal (#884).

        Returns:
            Sale: The new header, without a document number.
        """
        sale = Sale(
            date=datetime.now(),
            total_amount=totals["final_total"],
            tax_vat=totals["tax_vat"],
            tax_sscl=totals["tax_sscl"],
            net_revenue=totals["net_revenue"],
            payment_method=payments[0]["method"] if len(payments) == 1 else "SPLIT",
            loyalty_points_redeemed=totals.get("loyalty_points_redeemed", 0),
            loyalty_points_value=totals.get("loyalty_discount", Decimal("0.00")),
            user_id=cashier_id,
            customer_id=customer_id,
            terminal_id=ConfigService.get("terminal_id") or "TERM-01",
            origin_terminal_id=ConfigService.get("terminal_id") or "TERM-01",
            shift_id=shift_id,
        )
        sale._exempt_amount = totals.get("exempt_amount", Decimal("0"))
        return sale

    @staticmethod
    def _write_sale_lines(
        session: Session, sale: Sale, cart_items: list[dict[str, Any]], composite_map: dict[int, list[CompositeItem]]
    ) -> None:
        """Add a SaleItem per cart line and take its stock out (components for a composite).

        Args:
            session: The open session the sale is being written in.
            sale: The flushed sale (id and cashier set).
            cart_items: ``CartService.items``.
            composite_map: ``_fetch_composite_map`` result for the cart's products.
        """
        for item in cart_items:
            product = item["product"]
            qty = item["qty"]

            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                qty=qty,
                unit_price=item["unit_price"],
                original_price=item["original_price"],
                subtotal=item["total"],
                notes=item.get("note") or None,
            )
            session.add(sale_item)

            TransactionService._move_stock(session, composite_map, product.id, -qty, "SALE", sale.id, sale.user_id)

    @staticmethod
    def _load_receipt_relations(sale: Sale) -> None:
        """Load what the receipt needs while the session is still open (prevents DetachedInstanceError).

        Customer, cashier (also for a later print from ReceiptOptionsDialog,
        #681) and each line's product. The customer is loaded even for a
        walk-in sale: reading an unloaded ``sale.customer`` on the detached
        sale raises even when ``customer_id`` is None (#733). Payments are
        loaded where the sale event is built.

        Args:
            sale: The sale, still attached to its session.
        """
        _ = sale.customer
        _ = sale.user
        for item in sale.items:
            _ = item.product

    @staticmethod
    def _execute_sale(
        cart_service: CartService,
        payments: list,
        customer_id: int | None,
        peripherals: TransactionPeripherals,
        loyalty_points_redeemed: int = 0,
    ) -> Sale:
        """Write the sale in one transaction; see ``process_sale`` for the interface.

        Steps, in order: payment check, stock check, credit charge, sale
        header (numbered), credit ledger row, payments, lines + stock out,
        then load what the receipt needs. Any ValueError rolls everything back.
        """
        db = Database()
        with db.get_session() as session:
            # 0. Loyalty redemption validation & application (ADR-0002)
            if loyalty_points_redeemed > 0:
                raw_totals = cart_service.get_totals()
                pre_loyalty_total = raw_totals["subtotal"] - raw_totals["cart_discount"]
                can_redeem, reason = LoyaltyService.can_redeem_points(
                    customer_id, loyalty_points_redeemed, pre_loyalty_total, session=session
                )
                if not can_redeem:
                    raise ValueError(f"Loyalty redemption failed: {reason}")
                cart_service.set_loyalty_redemption(loyalty_points_redeemed)

            # 1. Validate payment, stock and cashier
            totals = cart_service.get_totals()
            total_amount = totals["final_total"]
            total_paid = sum(p["amount"] for p in payments)
            if total_paid < total_amount:
                raise ValueError(f"Insufficient payment. Paid: {total_paid}, Due: {total_amount}")

            # Pre-fetch composite items for all cart products (avoids N+1 queries later)
            cart_items = cart_service.items
            composite_map = TransactionService._fetch_composite_map(
                session, [item["product"].id for item in cart_items]
            )
            TransactionService._check_stock(session, cart_items, composite_map)

            current_user = AuthService.get_current_user()
            if not current_user:
                raise ValueError("No user logged in.")
            cashier_id = current_user.id

            # 2. Charge credit (ledger row follows once the sale has an id)
            credit_charge = TransactionService._charge_credit(session, payments, customer_id)

            # Look up open shift for this cashier on this terminal (#884)
            terminal_id = ConfigService.get("terminal_id") or "TERM-01"
            open_shift = session.scalars(
                select(Shift.id).where(
                    Shift.user_id == cashier_id,
                    Shift.terminal_id == terminal_id,
                    Shift.status == ShiftStatus.OPEN,
                )
            ).first()

            # 3. Write the numbered sale header, then its credit ledger row
            sale = TransactionService._new_sale(totals, payments, cashier_id, customer_id, shift_id=open_shift)
            TransactionService._insert_numbered(session, sale, "SALE")
            TransactionService._record_credit_charge(session, sale, credit_charge)

            # 4. Payments, then lines + stock out
            for p in payments:
                session.add(SalePayment(sale_id=sale.id, payment_method=p["method"], amount=p["amount"]))
            TransactionService._write_sale_lines(session, sale, cart_items, composite_map)

            # 4b. Loyalty redemption deduction (ADR-0002)
            if sale.loyalty_points_redeemed > 0:
                LoyaltyService.record_redemption(session, sale, sale.loyalty_points_redeemed)

            # 4c. Loyalty points earned on final bill (#747)
            LoyaltyService.record_sale_points(session, sale)

            # 5. Eager-load relationships before session closes (prevents DetachedInstanceError)
            TransactionService._load_receipt_relations(sale)

            # 6. The event carries the loaded, soon-detached sale (payments loaded here too)
            completed = SaleCompleted(sale, tuple(p.payment_method for p in sale.payments))

        # 7. Hardware -- only once the context manager has committed. The sale
        # is saved whatever the printer does, so a hardware error is only logged.
        try:
            peripherals.sale_completed(completed)
        except Exception as e:
            logger.error("Receipt/drawer for %s failed: %s", sale.document_number, e)
        return sale

    @staticmethod
    def get_void_reasons() -> list[dict]:
        """List the selectable void reason codes.

        Returns:
            list[dict]: ``{"id", "code", "description"}`` per VoidReason row, ordered by id.
        """
        db = Database()
        with db.get_session() as session:
            rows = session.query(VoidReason).order_by(VoidReason.id).all()
            return [{"id": r.id, "code": r.code, "description": r.description} for r in rows]

    @staticmethod
    def void_sale(sale_id: int, user_id: int, reason: str, reason_id: int | None = None) -> bool:
        """Mark sale as VOID and reverse stock deduction.

        Security: Caller must ensure user has permission.
        Uses StockService for proper audit trail and handles composites.

        Args:
            sale_id: ID of the sale to void.
            user_id: User performing the void.
            reason: Human-readable reason, written to the audit log.
            reason_id: Optional VoidReason id, stored on the document.

        Returns:
            bool: True if the sale was voided.
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
                if reason_id:
                    sale.void_reason_id = reason_id

                # Pre-fetch composite items for all products in sale
                product_ids = [item.product_id for item in sale.items]
                composite_map = TransactionService._fetch_composite_map(session, product_ids)

                # Reverse Stock via StockService
                for item in sale.items:
                    TransactionService._move_stock(
                        session, composite_map, item.product_id, item.qty, "VOID", sale.id, user_id
                    )

                # Give back any credit this sale put on the customer's book,
                # in this same transaction (#715).
                CustomerCreditService.reverse_credit_sale_in_session(
                    session, sale, "VOID", user_id, reference_doc=sale.document_number
                )

                # Give back any loyalty points earned on this sale (#747)
                LoyaltyService.reverse_sale_points(session, sale, reason="VOID")
                # Return any loyalty points redeemed on this sale (#755)
                LoyaltyService.return_redeemed_points(session, sale, reason="VOID")

                logger.info("VOID Sale %s by User %s: %s", sale.document_number, user_id, reason)

                log = AuditLog(
                    user_id=user_id,
                    action="VOID_SALE",
                    event_type="TRANSACTION",
                    details=f"Voided sale {sale.document_number}. Reason: {reason}",
                )
                session.add(log)
            return True
        except Exception as e:
            logger.error("Void Sale Failed: %s", e)
            return False

    @staticmethod
    def _build_refund_receipt(
        session: Session, original_sale: Sale, refund_sale: Sale, credit_reversed: Decimal = Decimal("0.00")
    ) -> list[dict] | None:
        """Build the refund voucher with `ReceiptBuilder` (None if it can't be built).

        A receipt problem must never undo a refund, so errors are logged.
        ``credit_reversed`` is the part taken off the customer's credit rather
        than handed back (#715); the voucher shows the split when it's non-zero.
        """
        try:
            authorizer = session.get(User, refund_sale.user_id)
            return ReceiptBuilder.build_refund_receipt(
                original_sale,
                refund_amount=original_sale.total_amount,
                authorized_by=authorizer.username if authorizer else "",
                refund_timestamp=refund_sale.date,
                credit_reversed=credit_reversed,
            )
        except Exception as e:
            logger.error("Could not build refund receipt for %s: %s", refund_sale.document_number, e)
            return None

    @staticmethod
    def refund_breakdown(sale_id: int) -> RefundBreakdown | None:
        """Split a full refund of a sale into money handed back and credit given back (#715).

        A refund of a credit sale takes the credit part off the customer's
        debt (``CustomerCreditService.reverse_credit_sale_in_session``), so
        only the rest is handed back -- the refund screens show both parts so
        a credit sale isn't paid back twice. Uses the same rule and cap as the
        reversal itself (``CustomerCreditService.credit_to_reverse``).

        Args:
            sale_id: ID of the original sale.

        Returns:
            The split, or None if the sale doesn't exist. A sale that is
            voided, already refunded, or itself a refund is not refundable and
            reports 0.00 for both parts.
        """
        db = Database()
        with db.get_session() as session:
            sale = session.get(Sale, sale_id)
            if not sale:
                return None

            customer = session.get(Customer, sale.customer_id) if sale.customer_id else None
            customer_name = customer.name if customer else ""
            total = Decimal(str(sale.total_amount or 0)).quantize(Precision.MONEY)
            already_refunded = session.query(Sale.id).filter(Sale.refund_of_sale_id == sale_id).first() is not None
            refundable = (
                sale.status != DocumentStatus.VOID
                and sale.payment_method != PaymentMethodType.REFUND
                and not already_refunded
            )
            if not refundable:
                return RefundBreakdown(total, ZERO_MONEY, ZERO_MONEY, customer_name)

            credit = CustomerCreditService.credit_to_reverse(session, sale)
            return RefundBreakdown(
                total=total,
                cash_back=refund_cash_back(total, credit),
                credit_reversed=credit,
                customer_name=customer_name,
            )

    @staticmethod
    def process_refund(
        original_sale_id: int,
        refund_reason: str,
        user_id: int,
        *,
        peripherals: TransactionPeripherals | None = None,
    ) -> bool:
        """
        Process a full refund for a previous sale.
        Creates a negative transaction and restores stock via StockService
        for proper audit trail.

        The refund voucher reaches the hardware through the peripherals port,
        only once the refund has committed (#734).

        Args:
            original_sale_id: ID of the original sale to refund
            refund_reason: Reason for the refund
            user_id: Current user ID processing the refund
            peripherals: Hardware adapter for this refund only; defaults to the
                installed one (``use_peripherals``).

        Returns:
            bool: True if the refund was committed (whatever the printer does).
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
                composite_map = TransactionService._fetch_composite_map(session, product_ids)

                # 2. Create refund transaction (negative values)
                # Mirror original sale's tax values (negated) to preserve
                # correct tax breakdown, especially for sales with exempt items.
                # Recalculating from the total would lose exempt-item granularity.
                refund_amount = -original_sale.total_amount
                refund_vat = -(original_sale.tax_vat or Decimal("0"))
                refund_sscl = -(original_sale.tax_sscl or Decimal("0"))
                refund_net = -(original_sale.net_revenue or Decimal("0"))

                terminal_id = ConfigService.get("terminal_id") or "TERM-01"
                open_shift = session.scalars(
                    select(Shift.id).where(
                        Shift.user_id == user_id,
                        Shift.terminal_id == terminal_id,
                        Shift.status == ShiftStatus.OPEN,
                    )
                ).first()

                refund_sale = Sale(
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
                    terminal_id=terminal_id,
                    origin_terminal_id=terminal_id,
                    shift_id=open_shift,
                )
                TransactionService._insert_numbered(session, refund_sale, "RETURN")
                refund_receipt_no = refund_sale.document_number

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

                    # 4. RESTORE stock via StockService (proper audit trail)
                    TransactionService._move_stock(
                        session,
                        composite_map,
                        original_item.product_id,
                        original_item.qty,
                        "RETURN",
                        refund_sale.id,
                        user_id,
                    )

                # 5. Give back any credit the original sale put on the
                # customer's book, in this same transaction (#715).
                credit_entry = CustomerCreditService.reverse_credit_sale_in_session(
                    session, original_sale, "REFUND", user_id, reference_doc=refund_receipt_no
                )
                credit_reversed = -credit_entry.amount if credit_entry else Decimal("0.00")

                # 5b. Give back any loyalty points earned on the original sale (#747)
                LoyaltyService.reverse_sale_points(session, original_sale, reason="REFUND")
                # 5c. Return any loyalty points redeemed on the original sale (#755)
                LoyaltyService.return_redeemed_points(session, original_sale, reason="REFUND")

                # 6. Create refund payment record
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

                log = AuditLog(
                    user_id=user_id,
                    action="REFUND",
                    event_type="TRANSACTION",
                    details=(
                        f"Refunded sale {original_sale.document_number} as {refund_receipt_no}. Reason: {refund_reason}"
                    ),
                )
                session.add(log)

                # 7. Build the refund voucher while items/products are loaded;
                # the event reaches the hardware only after the commit below.
                voucher = TransactionService._build_refund_receipt(session, original_sale, refund_sale, credit_reversed)
                completed = RefundCompleted(refund_sale, voucher)

        except Exception as e:
            logger.error("Refund Failed: %s", e)
            return False

        # 8. Hardware -- only once the context manager has committed. The
        # refund is saved whatever the printer does, so an error is only logged.
        try:
            (peripherals or TransactionService._peripherals).refund_completed(completed)
        except Exception as e:
            logger.error("Refund voucher for %s failed: %s", refund_receipt_no, e)
        return True

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
        from cbpos.core.models import User

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


# Backward compatibility — callers can still import from here
from cbpos.core.services.sale_query_service import SaleQueryService  # noqa: F401, E402
from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService  # noqa: F401, E402
