"""
Service for generating customer account statements.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any
from cbpos.core.database import Database
from cbpos.core.models import Customer, CustomerLedgerEntry
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


class StatementService:
    """Generates structured statement data for display, thermal print, or PDF export."""

    @staticmethod
    def generate_statement(
        customer_id: int,
        date_from: datetime,
        date_to: datetime,
    ) -> Dict[str, Any]:
        """
        Generate statement data for a customer within a date range.

        Args:
            customer_id: Customer ID.
            date_from: Start date.
            date_to: End date.

        Returns:
            Dictionary with customer info, entries, totals.
        """
        db = Database()
        with db.get_session() as session:
            customer = session.query(Customer).get(customer_id)
            if not customer:
                raise ValueError(f"Customer ID {customer_id} not found.")

            customer_data = {
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone,
                "current_debt": customer.current_debt,
                "credit_limit": customer.credit_limit,
            }
            session.expunge(customer)

        entries = CustomerCreditService.get_ledger(
            customer_id,
            date_from=date_from,
            date_to=date_to,
        )

        # Calculate totals
        total_debit = Decimal("0")
        total_credit = Decimal("0")

        if entries:
            opening_balance = entries[0].balance_after - entries[0].amount
            closing_balance = entries[-1].balance_after
        else:
            # No transactions in period — find the last known balance before start date
            opening_balance = StatementService._get_balance_before(db, customer_id, date_from)
            closing_balance = opening_balance

        rows: List[Dict[str, Any]] = []
        for entry in entries:
            if entry.amount > 0:
                total_debit += entry.amount
            else:
                total_credit += abs(entry.amount)

            rows.append(
                {
                    "date": entry.timestamp,
                    "type": entry.entry_type,
                    "description": entry.reference_doc or entry.note or entry.entry_type,
                    "debit": entry.amount if entry.amount > 0 else Decimal("0"),
                    "credit": abs(entry.amount) if entry.amount < 0 else Decimal("0"),
                    "balance": entry.balance_after,
                }
            )

        return {
            "customer": customer_data,
            "period_from": date_from,
            "period_to": date_to,
            "opening_balance": opening_balance,
            "entries": rows,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "closing_balance": closing_balance,
            "shop_name": ConfigService.get("shop_name") or "CB POS",
        }

    @staticmethod
    def _get_balance_before(db: Database, customer_id: int, date: datetime) -> Decimal:
        """Get the last known balance before a given date."""
        with db.get_session() as session:
            last_entry = (
                session.query(CustomerLedgerEntry)
                .filter(
                    CustomerLedgerEntry.customer_id == customer_id,
                    CustomerLedgerEntry.timestamp < date,
                )
                .order_by(CustomerLedgerEntry.timestamp.desc())
                .first()
            )
            if last_entry:
                balance = last_entry.balance_after
                session.expunge(last_entry)
                return balance
            return Decimal("0")
