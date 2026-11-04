from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind, ShiftStatus
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, CashMovement, Sale, SalePayment, Shift, User
from cbpos.core.services.config_service import ConfigService


class ShiftService:
    """Manages per-terminal cashier shifts: opening, cash movements, and cash-up reconciliation."""

    def __init__(self):
        """Bind this service instance to the database singleton."""
        self.db = Database()

    def start_shift(self, user_id: int, float_amount: Decimal, terminal_id: str | None = None) -> Shift:
        """Open a new shift for the user on the current (or specified) terminal with the given starting cash float.

        Raises:
            ValueError: If the user already has an open shift on this terminal.
        """
        with self.db.get_session() as session:
            terminal = terminal_id or ConfigService.get("terminal_id") or "TERM-01"

            # Check if user already has an open shift on this terminal
            existing_shift = session.scalars(
                select(Shift).where(
                    Shift.user_id == user_id,
                    Shift.terminal_id == terminal,
                    Shift.status == ShiftStatus.OPEN,
                )
            ).first()

            if existing_shift:
                raise ValueError("User already has an open shift on this terminal.")

            shift = Shift(
                user_id=user_id,
                starting_cash=float_amount,
                start_time=datetime.now(),
                status=ShiftStatus.OPEN,
                terminal_id=terminal,
            )
            session.add(shift)
            session.commit()
            session.refresh(shift)
            return shift

    def get_open_shift(self, user_id: int, terminal_id: str | None = None) -> Shift | None:
        """Return the user's currently open shift on this terminal, or None if none is open."""
        with self.db.get_session() as session:
            terminal = terminal_id or ConfigService.get("terminal_id") or "TERM-01"
            return session.scalars(
                select(Shift).where(
                    Shift.user_id == user_id,
                    Shift.terminal_id == terminal,
                    Shift.status == ShiftStatus.OPEN,
                )
            ).first()

    def get_current_shift(self, user_id: int, terminal_id: str | None = None) -> Shift | None:
        """Return the user's currently open shift on this terminal (alias for get_open_shift)."""
        return self.get_open_shift(user_id, terminal_id)

    def get_open_shifts(self, terminal_id: str | None = None) -> list[Shift]:
        """Return all currently open shifts, optionally filtered by terminal."""
        with self.db.get_session() as session:
            stmt = select(Shift).where(Shift.status == ShiftStatus.OPEN)
            if terminal_id:
                stmt = stmt.where(Shift.terminal_id == terminal_id)
            return list(session.scalars(stmt).all())

    def is_shift_stale(self, shift: Shift, current_terminal_id: str | None = None, max_age_hours: int = 24) -> bool:
        """Check whether an open shift is stale (> 24 hours old or on another terminal)."""
        if shift.status != ShiftStatus.OPEN:
            return False
        if shift.start_time and (datetime.now() - shift.start_time).total_seconds() > max_age_hours * 3600:
            return True
        return bool(current_terminal_id is not None and shift.terminal_id and shift.terminal_id != current_terminal_id)

    def get_stale_shifts(self, current_terminal_id: str | None = None, max_age_hours: int = 24) -> list[Shift]:
        """Return all open shifts that are stale."""
        with self.db.get_session() as session:
            shifts = session.scalars(select(Shift).where(Shift.status == ShiftStatus.OPEN)).all()
            return [s for s in shifts if self.is_shift_stale(s, current_terminal_id, max_age_hours)]

    def record_cash_movement(
        self, shift_id: int, type: str, amount: Decimal, reason: str, user_id: int
    ) -> CashMovement:
        """Record a manual cash movement (drop, payout, or in) against an open shift.

        Raises:
            ValueError: If the shift does not exist or is not open.
        """
        with self.db.get_session() as session:
            shift = session.get(Shift, shift_id)
            if not shift or shift.status != ShiftStatus.OPEN:
                raise ValueError("Shift is not open or does not exist.")

            movement = CashMovement(
                shift_id=shift_id,
                user_id=user_id,
                type=type,
                amount=amount,
                reason=reason,
                timestamp=datetime.now(),
            )
            session.add(movement)
            session.commit()
            session.refresh(movement)
            return movement

    def get_shift_summary(self, shift_id: int) -> dict[str, Any]:
        """Build a full reconciliation summary for a shift: sales by payment method, cash
        movements, expected drawer cash, void stats, transaction count, and VAT/SSCL totals.

        Expected cash is starting float + cash sales + cash-ins - drops - payouts. Can be
        called on an open or closed shift (an open shift covers up to "now").

        Raises:
            ValueError: If the shift does not exist.
        """
        with self.db.get_session() as session:
            shift = session.get(Shift, shift_id)
            if not shift:
                raise ValueError("Shift does not exist.")

            # Define shift matching clause: stamped shift_id or legacy terminal-matched fallback
            legacy_conditions = [
                Sale.shift_id.is_(None),
                Sale.user_id == shift.user_id,
                Sale.terminal_id == shift.terminal_id,
                Sale.date >= shift.start_time,
            ]
            if shift.end_time:
                legacy_conditions.append(Sale.date <= shift.end_time)

            shift_clause = or_(
                Sale.shift_id == shift.id,
                and_(*legacy_conditions),
            )

            # 1. Sales Breakdown by Payment Method (Display) and Kind (Reconciliation)
            sales_stmt = (
                select(
                    SalePayment.payment_method,
                    func.sum(SalePayment.amount).label("total"),
                )
                .join(Sale)
                .where(
                    shift_clause,
                    Sale.status == DocumentStatus.COMPLETED,
                )
                .group_by(SalePayment.payment_method)
            )
            sales_results = session.execute(sales_stmt).all()
            sales_by_method = {row[0]: row[1] for row in sales_results}

            kind_stmt = (
                select(
                    SalePayment.method_kind,
                    SalePayment.payment_method,
                    func.sum(SalePayment.amount).label("total"),
                )
                .join(Sale)
                .where(
                    shift_clause,
                    Sale.status == DocumentStatus.COMPLETED,
                )
                .group_by(SalePayment.method_kind, SalePayment.payment_method)
            )
            kind_results = session.execute(kind_stmt).all()
            from cbpos.core.services.payment_service import classify_method_name

            by_kind: dict[str, Decimal] = defaultdict(Decimal)
            for row in kind_results:
                k, name, total = row[0], row[1], row[2] or Decimal(0)
                if (k == PaymentMethodKind.OTHER or not k) and name:
                    inferred = classify_method_name(name)
                    by_kind[inferred] += total
                else:
                    by_kind[k] += total

            total_cash_sales = by_kind.get(PaymentMethodKind.CASH, Decimal(0))
            total_card_sales = by_kind.get(PaymentMethodKind.CARD, Decimal(0))
            total_credit_sales = by_kind.get(PaymentMethodKind.CREDIT, Decimal(0))
            total_qr_mobile = by_kind.get(PaymentMethodKind.QR, Decimal(0))
            total_cheque = by_kind.get(PaymentMethodKind.CHEQUE, Decimal(0))
            total_transfer = by_kind.get(PaymentMethodKind.TRANSFER, Decimal(0))
            total_sales = sum(sales_by_method.values())

            # 2. Cash Movements
            moves_stmt = select(CashMovement).where(CashMovement.shift_id == shift_id)
            if shift.end_time:
                moves_stmt = moves_stmt.where(CashMovement.timestamp <= shift.end_time)
            movements = session.scalars(moves_stmt).all()

            total_drops = sum(m.amount for m in movements if m.type == "DROP")
            total_payouts = sum(m.amount for m in movements if m.type == "PAYOUT" or m.type == "OUT")
            total_ins = sum(m.amount for m in movements if m.type == "IN")

            # 3. Expected Cash
            expected_cash = shift.starting_cash + total_cash_sales + total_ins - total_drops - total_payouts

            # 4. Audit Stats (Voids)
            void_stmt = select(func.count(Sale.id), func.sum(Sale.total_amount)).where(
                shift_clause,
                Sale.status == DocumentStatus.VOID,
            )
            void_count, void_value = session.execute(void_stmt).first()

            # Transaction Count
            txn_stmt = select(func.count(Sale.id)).where(
                shift_clause,
                Sale.status == DocumentStatus.COMPLETED,
            )
            txn_count = session.scalar(txn_stmt)

            # 5. Tax Totals for the shift
            tax_stmt = select(
                func.sum(Sale.tax_vat).label("total_vat"),
                func.sum(Sale.tax_sscl).label("total_sscl"),
            ).where(
                shift_clause,
                Sale.status == DocumentStatus.COMPLETED,
            )
            tax_row = session.execute(tax_stmt).first()

            return {
                "shift_id": shift.id,
                "user_name": shift.user.username,
                "start_time": shift.start_time,
                "end_time": shift.end_time,
                "starting_cash": shift.starting_cash,
                "sales_by_method": sales_by_method,
                "total_sales": total_sales,
                "cash_sales": total_cash_sales,
                "card_sales": total_card_sales,
                "credit_sales": total_credit_sales,
                "qr_mobile_sales": total_qr_mobile,
                "cheque_sales": total_cheque,
                "transfer_sales": total_transfer,
                "cash_in": total_ins,
                "cash_out": total_payouts + total_drops,
                "expected_cash": expected_cash,
                "void_count": void_count or 0,
                "void_value": void_value or Decimal(0),
                "txn_count": txn_count or 0,
                "total_vat": tax_row[0] or Decimal(0) if tax_row else Decimal(0),
                "total_sscl": tax_row[1] or Decimal(0) if tax_row else Decimal(0),
            }

    def close_shift(
        self,
        shift_id: int,
        counted_cash: Decimal,
        notes: str = None,
        reason_category: str = None,
    ) -> dict[str, Any]:
        """Close an open shift, comparing physically counted cash against the expected total.

        Persists the counted/expected cash, the shortage/overage reason category, and the
        free-text notes on the shift, and returns the shift summary (see `get_shift_summary`)
        augmented with `end_time`, `actual_cash`, `variance` (counted minus expected), and
        `notes`.

        Raises:
            ValueError: If the shift does not exist or is already closed.
        """
        with self.db.get_session() as session:
            shift = session.get(Shift, shift_id)
            if not shift or shift.status != ShiftStatus.OPEN:
                raise ValueError("Shift is not open or does not exist.")

            summary = self.get_shift_summary(shift_id)
            expected_cash = summary["expected_cash"]
            variance = counted_cash - expected_cash

            # Update Shift
            shift.end_time = datetime.now()
            shift.actual_cash = counted_cash
            shift.expected_cash = expected_cash
            shift.status = ShiftStatus.CLOSED
            shift.reason_category = reason_category
            shift.notes = notes

            session.commit()

            # Return full summary with closing details
            summary["end_time"] = shift.end_time
            summary["actual_cash"] = counted_cash
            summary["variance"] = variance
            summary["notes"] = notes

            return summary

    def force_close_shift(
        self,
        shift_id: int,
        counted_cash: Decimal | None,
        reason: str,
        closed_by_user_id: int,
    ) -> Shift:
        """Force-close a stale or orphaned shift (requires shift.force_close permission).

        Records SHIFT_FORCE_CLOSED in the audit log.
        """
        with self.db.get_session() as session:
            closed_by = session.get(User, closed_by_user_id)
            has_permission = False
            if closed_by and closed_by.role:
                has_permission = any(p.code == Permissions.SHIFT_FORCE_CLOSE for p in closed_by.role.permissions)
            if not has_permission:
                raise ValueError(f"Permission denied: {Permissions.SHIFT_FORCE_CLOSE} required to force-close shifts.")

            shift = session.get(Shift, shift_id)
            if not shift or shift.status != ShiftStatus.OPEN:
                raise ValueError("Shift is not open or does not exist.")

            summary = self.get_shift_summary(shift_id)
            expected_cash = summary["expected_cash"]

            shift.end_time = datetime.now()
            shift.expected_cash = expected_cash
            shift.actual_cash = counted_cash
            shift.status = ShiftStatus.CLOSED
            reason_note = f"[Force-closed: {reason}]"
            shift.notes = f"{shift.notes} {reason_note}".strip() if shift.notes else reason_note

            audit = AuditLog(
                user_id=closed_by_user_id,
                action="Shift Force Closed",
                event_type="SHIFT_FORCE_CLOSED",
                terminal_id=ConfigService.get("terminal_id") or "TERM-01",
                details=f"Shift #{shift.id} (terminal {shift.terminal_id}, cashier {shift.user_id}) force-closed: counted={counted_cash}, reason={reason}",
                timestamp=datetime.now(),
            )
            session.add(audit)
            session.commit()
            session.refresh(shift)
            return shift
