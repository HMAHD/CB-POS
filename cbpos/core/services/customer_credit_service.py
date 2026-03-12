import logging
from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import func
from cbpos.core.database import Database
from cbpos.core.models import Customer, CustomerPayment, CustomerLedgerEntry

logger = logging.getLogger(__name__)


class CustomerCreditService:
    """Service for managing customer credit book: payments, ledger entries, overdue tracking."""

    @staticmethod
    def record_payment(
        customer_id: int,
        amount: Decimal,
        payment_method: str,
        user_id: int,
        reference: Optional[str] = None,
        note: Optional[str] = None,
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
        session: Any,
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
            return True

    @staticmethod
    def get_ledger(
        customer_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[CustomerLedgerEntry]:
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

            entries = query.order_by(CustomerLedgerEntry.timestamp.asc()).all()
            for entry in entries:
                session.expunge(entry)
            return entries

    @staticmethod
    def get_overdue_customers() -> List[Dict[str, Any]]:
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
                .all()
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
    def get_customer_summary(customer_id: int) -> Dict[str, Any]:
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

            # Total purchases (sum of positive ledger amounts)
            total_purchases = (
                session.query(func.coalesce(func.sum(CustomerLedgerEntry.amount), 0))
                .filter(
                    CustomerLedgerEntry.customer_id == customer_id,
                    CustomerLedgerEntry.entry_type == "SALE",
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
