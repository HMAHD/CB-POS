"""Service for managing supplier payables: payments, ledger entries, overdue tracking."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func

from cbpos.core.database import Database
from cbpos.core.models import Supplier, SupplierLedgerEntry, SupplierPayment
from cbpos.core.utils.aging import oldest_open_charge
from cbpos.core.utils.date_ranges import range_for

logger = logging.getLogger(__name__)


class SupplierPayableService:
    """Service for supplier payable tracking, mirroring CustomerCreditService."""

    @staticmethod
    def record_payment(
        supplier_id: int,
        amount: Decimal,
        payment_method: str,
        user_id: int,
        reference: str | None = None,
        note: str | None = None,
    ) -> SupplierPayment:
        """
        Record a payment made to a supplier.

        Args:
            supplier_id: The supplier being paid.
            amount: Payment amount (must be > 0 and <= current_payable).
            payment_method: Cash, Card, Transfer, Cheque.
            user_id: User recording the payment.
            reference: Optional cheque number or transfer reference.
            note: Optional note.

        Returns:
            The created SupplierPayment record.

        Raises:
            ValueError: If validation fails.
        """
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        db = Database()
        with db.get_session() as session:
            supplier = session.get(Supplier, supplier_id, with_for_update=True)
            if not supplier:
                raise ValueError("Supplier not found.")

            if amount > supplier.current_payable:
                raise ValueError(f"Payment amount ({amount}) exceeds outstanding payable ({supplier.current_payable}).")

            # Create payment record
            payment = SupplierPayment(
                supplier_id=supplier_id,
                amount=amount,
                payment_method=payment_method,
                reference=reference,
                note=note,
                user_id=user_id,
            )
            session.add(payment)
            session.flush()

            # Decrement payable
            supplier.current_payable -= amount

            # Create ledger entry (negative = payment)
            entry = SupplierLedgerEntry(
                supplier_id=supplier_id,
                entry_type="PAYMENT",
                amount=-amount,
                balance_after=supplier.current_payable,
                reference_id=payment.id,
                reference_doc=f"PMT-{payment.id}",
                note=note or f"{payment_method} payment",
                user_id=user_id,
            )
            session.add(entry)

            logger.info(
                "Supplier payment recorded: Supplier %d, Amount %s, Method %s, New Payable %s",
                supplier_id,
                amount,
                payment_method,
                supplier.current_payable,
            )

            session.flush()
            session.expunge(payment)
            return payment

    @staticmethod
    def record_purchase_in_session(
        session: Any,
        supplier_id: int,
        purchase_id: int,
        amount: Decimal,
        doc_number: str,
        balance_after: Decimal,
        user_id: int,
    ) -> None:
        """
        Record a ledger entry for a purchase within an existing session.
        Called from PurchaseService.commit_purchase() to keep everything in one transaction.

        Args:
            session: SQLAlchemy session.
            supplier_id: Supplier ID.
            purchase_id: Purchase document ID.
            amount: Purchase total (positive = increases payable).
            doc_number: GRN document number.
            balance_after: Supplier's payable balance after this entry.
            user_id: User who committed the purchase.
        """
        entry = SupplierLedgerEntry(
            supplier_id=supplier_id,
            entry_type="PURCHASE",
            amount=amount,
            balance_after=balance_after,
            reference_id=purchase_id,
            reference_doc=doc_number,
            note="Purchase received",
            user_id=user_id,
        )
        session.add(entry)

    @staticmethod
    def record_adjustment(
        supplier_id: int,
        amount: Decimal,
        note: str,
        user_id: int,
    ) -> bool:
        """
        Record a balance adjustment (correction).

        Args:
            supplier_id: Supplier to adjust.
            amount: Positive increases payable, negative decreases payable.
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
            supplier = session.get(Supplier, supplier_id, with_for_update=True)
            if not supplier:
                raise ValueError("Supplier not found.")

            supplier.current_payable += amount

            entry = SupplierLedgerEntry(
                supplier_id=supplier_id,
                entry_type="ADJUSTMENT",
                amount=amount,
                balance_after=supplier.current_payable,
                note=note,
                user_id=user_id,
            )
            session.add(entry)

            logger.info(
                "Supplier adjustment: Supplier %d, Amount %s, New Payable %s, Note: %s",
                supplier_id,
                amount,
                supplier.current_payable,
                note,
            )
            return True

    @staticmethod
    def get_ledger(
        supplier_id: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[SupplierLedgerEntry]:
        """
        Get chronological ledger entries for a supplier.

        Args:
            supplier_id: Supplier ID.
            date_from: Optional start date filter.
            date_to: Optional end date filter.

        Returns:
            List of SupplierLedgerEntry ordered by timestamp.
        """
        start_dt, end_dt = range_for(date_from, date_to)
        db = Database()
        with db.get_session() as session:
            query = session.query(SupplierLedgerEntry).filter(SupplierLedgerEntry.supplier_id == supplier_id)

            if start_dt:
                query = query.filter(SupplierLedgerEntry.timestamp >= start_dt)
            if end_dt:
                query = query.filter(SupplierLedgerEntry.timestamp < end_dt)

            entries = query.order_by(SupplierLedgerEntry.timestamp.asc()).all()
            for entry in entries:
                session.expunge(entry)
            return entries

    @staticmethod
    def oldest_unpaid_charge_date(supplier_id: int) -> date | None:
        """Find the date of the supplier's oldest unpaid purchase using FIFO allocation (#897)."""
        entries = SupplierPayableService.get_ledger(supplier_id)
        return oldest_open_charge(
            entries,
            charge_types={"PURCHASE", "ADJUSTMENT"},
            credit_types={"PAYMENT", "REFUND", "ADJUSTMENT"},
        )

    @staticmethod
    def get_overdue_suppliers() -> list[dict[str, Any]]:
        """
        Get suppliers with outstanding payable who are overdue based on payment_terms.

        Uses FIFO matching of purchases against credits so new purchases do not reset the aging clock.

        Returns:
            List of dicts with supplier info and overdue days.
        """
        db = Database()
        with db.get_session() as session:
            suppliers = (
                session.query(Supplier)
                .filter(
                    Supplier.current_payable > 0,
                    Supplier.payment_terms > 0,
                    Supplier.is_active.is_(True),
                )
                .all()
            )

            results = []
            today = date.today()

            # Pre-fetch latest payment timestamp per supplier to avoid N+1 queries
            supplier_ids = [s.id for s in suppliers]

            latest_payments_subq = (
                session.query(
                    SupplierLedgerEntry.supplier_id,
                    func.max(SupplierLedgerEntry.timestamp).label("last_payment"),
                )
                .filter(
                    SupplierLedgerEntry.supplier_id.in_(supplier_ids),
                    SupplierLedgerEntry.entry_type == "PAYMENT",
                )
                .group_by(SupplierLedgerEntry.supplier_id)
                .all()
            )
            last_payment_map = {row.supplier_id: row.last_payment for row in latest_payments_subq}

            for supplier in suppliers:
                oldest_charge_date = SupplierPayableService.oldest_unpaid_charge_date(supplier.id)
                if oldest_charge_date is None:
                    continue

                days_since = (today - oldest_charge_date).days

                if days_since > supplier.payment_terms:
                    results.append(
                        {
                            "id": supplier.id,
                            "company_name": supplier.company_name,
                            "phone": supplier.phone or "",
                            "outstanding": supplier.current_payable,
                            "payment_terms": supplier.payment_terms,
                            "days_overdue": days_since - supplier.payment_terms,
                            "last_payment_date": last_payment_map.get(supplier.id),
                        }
                    )

            results.sort(key=lambda x: x["days_overdue"], reverse=True)
            return results

            results.sort(key=lambda x: x["days_overdue"], reverse=True)
            return results

    @staticmethod
    def get_supplier_summary(supplier_id: int) -> dict[str, Any]:
        """
        Get a summary of a supplier's payable status.

        Returns:
            Dict with current_payable, payment_terms, last_payment_date,
            total_purchases, total_payments.
        """
        db = Database()
        with db.get_session() as session:
            supplier = session.get(Supplier, supplier_id)
            if not supplier:
                return {}

            total_purchases = (
                session.query(func.coalesce(func.sum(SupplierLedgerEntry.amount), 0))
                .filter(
                    SupplierLedgerEntry.supplier_id == supplier_id,
                    SupplierLedgerEntry.entry_type == "PURCHASE",
                )
                .scalar()
            )

            total_payments = (
                session.query(func.coalesce(func.sum(func.abs(SupplierLedgerEntry.amount)), 0))
                .filter(
                    SupplierLedgerEntry.supplier_id == supplier_id,
                    SupplierLedgerEntry.entry_type == "PAYMENT",
                )
                .scalar()
            )

            last_payment = (
                session.query(SupplierLedgerEntry)
                .filter(
                    SupplierLedgerEntry.supplier_id == supplier_id,
                    SupplierLedgerEntry.entry_type == "PAYMENT",
                )
                .order_by(SupplierLedgerEntry.timestamp.desc())
                .first()
            )

            return {
                "current_payable": supplier.current_payable,
                "payment_terms": supplier.payment_terms,
                "last_payment_date": last_payment.timestamp if last_payment else None,
                "total_purchases": Decimal(str(total_purchases)),
                "total_payments": Decimal(str(total_payments)),
            }
