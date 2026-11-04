import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from cbpos.core.constants.status import PaymentMethodKind, PaymentMethodType, Precision
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Customer, CustomerLedgerEntry, CustomerPayment, Sale, SalePayment, User

logger = logging.getLogger(__name__)

# Ledger entry types that give back credit a sale put on the book (#715).
CREDIT_REVERSAL_TYPES: tuple[str, ...] = ("VOID", "REFUND")


class CustomerCreditService:
    """Service for managing customer credit book: payments, ledger entries, overdue tracking."""

    @staticmethod
    def record_payment(
        customer_id: int,
        amount: Decimal,
        payment_method: str,
        user_id: int,
        reference: str | None = None,
        note: str | None = None,
    ) -> CustomerPayment:
        """
        Record a customer payment against their existing debt.

        Uses serializable isolation and row-level locking to prevent
        concurrent terminals from corrupting the customer balance.

        Args:
            customer_id: The customer making the payment.
            amount: Payment amount (must be > 0 and <= current_debt).
            payment_method: Cash, Card, Transfer, Cheque.
            user_id: User recording the payment.
            reference: Optional cheque number or transfer reference.
            note: Optional note.

        Returns:
            The created CustomerPayment record.

        Raises:
            ValueError: If validation fails.
        """
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        db = Database()
        with db.get_session(serializable=True) as session:
            customer = session.get(Customer, customer_id, with_for_update=True)
            if not customer:
                raise ValueError("Customer not found.")

            if amount > customer.current_debt:
                raise ValueError(f"Payment amount ({amount}) exceeds outstanding debt ({customer.current_debt}).")

            # Create payment record
            payment = CustomerPayment(
                customer_id=customer_id,
                amount=amount,
                payment_method=payment_method,
                reference=reference,
                note=note,
                user_id=user_id,
            )
            session.add(payment)
            session.flush()

            # Decrement debt
            customer.current_debt -= amount

            # Create ledger entry (negative = payment)
            entry = CustomerLedgerEntry(
                customer_id=customer_id,
                entry_type="PAYMENT",
                amount=-amount,
                balance_after=customer.current_debt,
                reference_id=payment.id,
                reference_doc=f"PMT-{payment.id}",
                note=note or f"{payment_method} payment",
                user_id=user_id,
            )
            session.add(entry)

            logger.info(
                "Payment recorded: Customer %d, Amount %s, Method %s, New Debt %s",
                customer_id,
                amount,
                payment_method,
                customer.current_debt,
            )

            log = AuditLog(
                user_id=user_id,
                action="CREDIT_PAYMENT",
                event_type="CREDIT",
                details=(
                    f"Recorded {payment_method} payment of {amount:.2f} for {customer.name}. "
                    f"New balance: {customer.current_debt:.2f}."
                ),
            )
            session.add(log)

            # Expunge for safe return
            session.flush()
            session.expunge(payment)
            return payment

    @staticmethod
    def record_credit_sale(
        customer_id: int,
        sale_id: int,
        amount: Decimal,
        doc_number: str,
        user_id: int,
    ) -> None:
        """
        Record a ledger entry for a credit sale.
        Called from TransactionService after a credit sale is processed.

        Args:
            customer_id: Customer who bought on credit.
            sale_id: The sale ID.
            amount: Credit amount (positive).
            doc_number: Document/receipt number.
            user_id: Cashier who processed the sale.
        """
        db = Database()
        with db.get_session(serializable=True) as session:
            customer = session.get(Customer, customer_id, with_for_update=True)
            if not customer:
                logger.warning("record_credit_sale: Customer %d not found", customer_id)
                return

            # Increment debt atomically under row lock
            customer.current_debt += amount

            entry = CustomerLedgerEntry(
                customer_id=customer_id,
                entry_type="SALE",
                amount=amount,
                balance_after=customer.current_debt,
                reference_id=sale_id,
                reference_doc=doc_number,
                note="Credit sale",
                user_id=user_id,
            )
            session.add(entry)

    @staticmethod
    def record_credit_sale_in_session(
        session: Session,
        customer_id: int,
        sale_id: int,
        amount: Decimal,
        doc_number: str,
        balance_after: Decimal,
        user_id: int,
    ) -> None:
        """
        Record a ledger entry for a credit sale within an existing session.
        Used by TransactionService to keep everything in one transaction.
        """
        entry = CustomerLedgerEntry(
            customer_id=customer_id,
            entry_type="SALE",
            amount=amount,
            balance_after=balance_after,
            reference_id=sale_id,
            reference_doc=doc_number,
            note="Credit sale",
            user_id=user_id,
        )
        session.add(entry)

    @staticmethod
    def credit_to_reverse(session: Session, sale: Sale, refund_amount: Decimal | None = None) -> Decimal:
        """How much credit a void/refund of ``sale`` gives back -- without writing anything.

        The single source of the rule used by ``reverse_credit_sale_in_session``
        and by the refund screens' cash/credit split (#715): the sale's credit
        payments, less what earlier VOID/REFUND entries already gave back, and
        for a partial refund only its proportional share (see
        ``reverse_credit_sale_in_session``).

        Args:
            session: Open DB session.
            sale: The original sale.
            refund_amount: Positive amount refunded for a partial refund; None
                for a full void/refund.

        Returns:
            Credit to give back (0.00 when the sale has no credit left on the book).
        """
        zero = Decimal("0.00")
        if not sale.customer_id:
            return zero

        credit_portion = Decimal(
            str(
                session.query(func.coalesce(func.sum(SalePayment.amount), 0))
                .filter(
                    SalePayment.sale_id == sale.id,
                    or_(
                        SalePayment.method_kind == PaymentMethodKind.CREDIT,
                        func.upper(SalePayment.payment_method) == PaymentMethodType.CREDIT.upper(),
                    ),
                )
                .scalar()
            )
        )
        if credit_portion <= 0:
            return zero

        already_reversed = -Decimal(
            str(
                session.query(func.coalesce(func.sum(CustomerLedgerEntry.amount), 0))
                .filter(
                    CustomerLedgerEntry.customer_id == sale.customer_id,
                    CustomerLedgerEntry.reference_id == sale.id,
                    CustomerLedgerEntry.entry_type.in_(CREDIT_REVERSAL_TYPES),
                )
                .scalar()
            )
        )
        remaining = credit_portion - already_reversed

        reversal = remaining
        if refund_amount is not None:
            sale_total = Decimal(str(sale.total_amount or 0))
            if sale_total > 0:
                share = (credit_portion * Decimal(str(refund_amount)) / sale_total).quantize(Precision.MONEY)
                reversal = min(share, remaining)
        reversal = reversal.quantize(Precision.MONEY)
        if reversal <= 0 or session.get(Customer, sale.customer_id) is None:
            return zero
        return reversal

    @staticmethod
    def reverse_credit_sale_in_session(
        session: Session,
        sale: Sale,
        entry_type: str,
        user_id: int,
        reference_doc: str,
        refund_amount: Decimal | None = None,
    ) -> CustomerLedgerEntry | None:
        """Give back the credit a sale put on the customer's book (#715).

        Called by TransactionService inside the void/refund transaction, so
        the debt and its ledger row commit (or roll back) with the void or
        refund itself. The row is an ordinary ``CustomerLedgerEntry`` with
        ``synced = False``, so LAN Sync pushes it and the Main PC moves its
        balance by the same amount, exactly as for a credit sale or payment.

        Only the credit part of the sale is reversed: a sale paid 120 cash +
        80 credit gives back 80 of debt; the cash part is not the credit
        book's business.

        Partial refunds: the credit given back is the refund's share of the
        sale's credit, i.e. ``credit * refund_amount / sale total`` -- each
        refunded rupee is split between credit and cash in the same ratio the
        sale was paid. The total ever reversed for one sale is capped at what
        the sale put on credit, so repeated partial refunds (or a void after a
        refund) can never take back more than was owed.

        The balance is not clamped at zero: if the customer already paid the
        debt off, the shop now owes them, and a negative balance says so.
        (The Main PC applies the same amount unclamped, so both agree.)

        Args:
            session: The open session of the void/refund.
            sale: The original sale being voided or refunded.
            entry_type: ``"VOID"`` or ``"REFUND"``.
            user_id: User performing the void/refund.
            reference_doc: Document number shown in the credit book -- the
                voided sale's, or the refund receipt's.
            refund_amount: Positive amount refunded, for a partial refund;
                None reverses all the credit still outstanding on the sale.

        Returns:
            The new ledger entry, or None if nothing was owed on credit.
        """
        if entry_type not in CREDIT_REVERSAL_TYPES:
            raise ValueError(f"Unsupported credit reversal type: {entry_type}")
        session.flush()  # earlier reversals of this sale in the same session count too
        reversal = CustomerCreditService.credit_to_reverse(session, sale, refund_amount)
        if reversal <= 0:
            return None

        customer = session.get(Customer, sale.customer_id, with_for_update=True)
        if not customer:
            logger.warning("Credit reversal: customer %d of sale %s not found", sale.customer_id, sale.id)
            return None

        customer.current_debt = (customer.current_debt or Decimal("0.00")) - reversal
        entry = CustomerLedgerEntry(
            customer_id=customer.id,
            entry_type=entry_type,
            amount=-reversal,
            balance_after=customer.current_debt,
            reference_id=sale.id,
            reference_doc=reference_doc,
            note=f"{entry_type.title()} of {sale.document_number}",
            user_id=user_id,
        )
        session.add(entry)
        session.add(
            AuditLog(
                user_id=user_id,
                action="CREDIT_REVERSAL",
                event_type="CREDIT",
                details=(
                    f"{entry_type.title()} of credit sale {sale.document_number} gave back {reversal:.2f} "
                    f"to {customer.name}. New balance: {customer.current_debt:.2f}."
                ),
            )
        )
        logger.info(
            "Credit reversal (%s): Customer %d, Sale %s, Amount %s, New Debt %s",
            entry_type,
            customer.id,
            sale.document_number,
            reversal,
            customer.current_debt,
        )
        return entry

    @staticmethod
    def record_adjustment(
        customer_id: int,
        amount: Decimal,
        note: str,
        user_id: int,
    ) -> bool:
        """
        Record a balance adjustment (correction).

        Args:
            customer_id: Customer to adjust.
            amount: Positive increases debt, negative decreases debt.
            note: Reason for adjustment (required).
            user_id: User making the adjustment.

        Returns:
            True if successful.

        Raises:
            ValueError: If validation fails.
        """
        if not note:
            raise ValueError("Adjustment note is required.")

        db = Database()
        with db.get_session() as session:
            customer = session.get(Customer, customer_id, with_for_update=True)
            if not customer:
                raise ValueError("Customer not found.")

            customer.current_debt += amount
            if customer.current_debt < 0:
                customer.current_debt = Decimal("0.00")

            entry = CustomerLedgerEntry(
                customer_id=customer_id,
                entry_type="ADJUSTMENT",
                amount=amount,
                balance_after=customer.current_debt,
                note=note,
                user_id=user_id,
            )
            session.add(entry)

            logger.info(
                "Balance adjustment: Customer %d, Amount %s, New Debt %s, Note: %s",
                customer_id,
                amount,
                customer.current_debt,
                note,
            )

            log = AuditLog(
                user_id=user_id,
                action="CREDIT_ADJUSTMENT",
                event_type="CREDIT",
                details=(
                    f"Adjusted {customer.name}'s balance by {amount:.2f}. "
                    f"New balance: {customer.current_debt:.2f}. Note: {note}"
                ),
            )
            session.add(log)
            return True

    @staticmethod
    def get_ledger(
        customer_id: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[CustomerLedgerEntry]:
        """
        Get chronological ledger entries for a customer.

        Args:
            customer_id: Customer ID.
            date_from: Optional start date filter.
            date_to: Optional end date filter.

        Returns:
            List of CustomerLedgerEntry ordered by timestamp.
        """
        db = Database()
        with db.get_session() as session:
            query = session.query(CustomerLedgerEntry).filter(CustomerLedgerEntry.customer_id == customer_id)

            if date_from:
                query = query.filter(CustomerLedgerEntry.timestamp >= date_from)
            if date_to:
                query = query.filter(CustomerLedgerEntry.timestamp <= date_to)

            entries = []
            for entry in query.order_by(CustomerLedgerEntry.timestamp.asc()).yield_per(500):
                session.expunge(entry)
                entries.append(entry)
            return entries

    @staticmethod
    def get_overdue_customers() -> list[dict[str, Any]]:
        """
        Get customers with outstanding debt who are overdue based on payment_terms.

        Returns:
            List of dicts with customer info and days since last activity.
        """
        db = Database()
        with db.get_session() as session:
            # Customers with debt > 0 and payment_terms > 0
            customers = (
                session.query(Customer)
                .filter(Customer.current_debt > 0, Customer.payment_terms > 0, Customer.is_active.is_(True))
                .yield_per(500)
            )

            results = []
            now = datetime.now()

            for customer in customers:
                # Find the most recent ledger entry (last activity)
                last_entry = (
                    session.query(CustomerLedgerEntry)
                    .filter(CustomerLedgerEntry.customer_id == customer.id)
                    .order_by(CustomerLedgerEntry.timestamp.desc())
                    .first()
                )

                if last_entry:
                    days_since = (now - last_entry.timestamp).days
                else:
                    days_since = 999  # No ledger entries, treat as very overdue

                # Overdue if days_since > payment_terms
                if days_since > customer.payment_terms:
                    # Find last payment date specifically
                    last_payment = (
                        session.query(CustomerLedgerEntry)
                        .filter(
                            CustomerLedgerEntry.customer_id == customer.id,
                            CustomerLedgerEntry.entry_type == "PAYMENT",
                        )
                        .order_by(CustomerLedgerEntry.timestamp.desc())
                        .first()
                    )

                    results.append(
                        {
                            "id": customer.id,
                            "name": customer.name,
                            "phone": customer.phone or "",
                            "outstanding": customer.current_debt,
                            "credit_limit": customer.credit_limit,
                            "payment_terms": customer.payment_terms,
                            "days_overdue": days_since - customer.payment_terms,
                            "last_payment_date": last_payment.timestamp if last_payment else None,
                        }
                    )

            # Sort by days overdue descending
            results.sort(key=lambda x: x["days_overdue"], reverse=True)
            return results

    @staticmethod
    def get_customer_summary(customer_id: int) -> dict[str, Any]:
        """
        Get a summary of a customer's credit status.

        Returns:
            Dict with current_debt, credit_limit, available, last_payment_date,
            total_purchases, total_payments.
        """
        db = Database()
        with db.get_session() as session:
            customer = session.get(Customer, customer_id)
            if not customer:
                return {}

            # Total purchases on credit, net of voided/refunded credit sales
            total_purchases = (
                session.query(func.coalesce(func.sum(CustomerLedgerEntry.amount), 0))
                .filter(
                    CustomerLedgerEntry.customer_id == customer_id,
                    CustomerLedgerEntry.entry_type.in_(("SALE", *CREDIT_REVERSAL_TYPES)),
                )
                .scalar()
            )

            # Total payments (sum of negative ledger amounts, returned as positive)
            total_payments = (
                session.query(func.coalesce(func.sum(func.abs(CustomerLedgerEntry.amount)), 0))
                .filter(
                    CustomerLedgerEntry.customer_id == customer_id,
                    CustomerLedgerEntry.entry_type == "PAYMENT",
                )
                .scalar()
            )

            # Last payment date
            last_payment = (
                session.query(CustomerLedgerEntry)
                .filter(
                    CustomerLedgerEntry.customer_id == customer_id,
                    CustomerLedgerEntry.entry_type == "PAYMENT",
                )
                .order_by(CustomerLedgerEntry.timestamp.desc())
                .first()
            )

            available = customer.credit_limit - customer.current_debt

            return {
                "current_debt": customer.current_debt,
                "credit_limit": customer.credit_limit,
                "available": available if available > 0 else Decimal("0.00"),
                "last_payment_date": last_payment.timestamp if last_payment else None,
                "total_purchases": Decimal(str(total_purchases)),
                "total_payments": Decimal(str(total_payments)),
                "payment_terms": customer.payment_terms,
            }

    @staticmethod
    def backfill_missing_ledger_entries(session: Session | None = None) -> int:
        """Find any customer with current_debt > 0 and no ledger entries, and insert an OPENING entry.

        Runs idempotently on startup or migration. Returns the count of backfilled entries.
        """

        def _do_backfill(sess: Session) -> int:
            from datetime import timedelta

            customers_with_debt = sess.query(Customer).filter(Customer.current_debt > Decimal("0.00")).yield_per(500)
            count = 0
            default_timestamp = datetime.now() - timedelta(days=30)
            target_user_id = None

            for cust in customers_with_debt:
                if target_user_id is None:
                    user = sess.query(User).order_by(User.id).first()
                    if not user:
                        user = User(username="system", pin_hash="system")
                        sess.add(user)
                        sess.flush()
                    target_user_id = user.id

                existing_count = (
                    sess.query(CustomerLedgerEntry).filter(CustomerLedgerEntry.customer_id == cust.id).count()
                )
                if existing_count == 0:
                    entry = CustomerLedgerEntry(
                        customer_id=cust.id,
                        entry_type="OPENING",
                        amount=cust.current_debt,
                        balance_after=cust.current_debt,
                        reference_doc="INIT-BAL",
                        note="Opening Balance",
                        user_id=target_user_id,
                        timestamp=cust.last_modified or default_timestamp,
                    )
                    sess.add(entry)
                    count += 1
            if count > 0:
                sess.flush()
                logger.info("Backfilled %d missing customer opening ledger entries.", count)
            return count

        if session is not None:
            return _do_backfill(session)

        with Database().get_session() as sess:
            res = _do_backfill(sess)
            sess.commit()
            return res
