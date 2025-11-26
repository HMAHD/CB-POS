from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy import select, func
from cbpos.core.database import Database
from cbpos.core.models import Shift, CashMovement, Sale, SalePayment


class ShiftService:
    def __init__(self):
        self.db = Database()

    def start_shift(self, user_id: int, float_amount: Decimal) -> Shift:
        with self.db.get_session() as session:
            # Check if user already has an open shift
            existing_shift = session.scalars(
                select(Shift).where(Shift.user_id == user_id, Shift.status == "OPEN")
            ).first()

            if existing_shift:
                raise ValueError("User already has an open shift.")

            shift = Shift(
                user_id=user_id,
                starting_cash=float_amount,
                start_time=datetime.now(),
                status="OPEN",
            )
            session.add(shift)
            session.commit()
            session.refresh(shift)
            return shift

    def get_current_shift(self, user_id: int) -> Optional[Shift]:
        with self.db.get_session() as session:
            return session.scalars(
                select(Shift).where(Shift.user_id == user_id, Shift.status == "OPEN")
            ).first()

    def record_cash_movement(
        self, shift_id: int, type: str, amount: Decimal, reason: str, user_id: int
    ) -> CashMovement:
        with self.db.get_session() as session:
            shift = session.get(Shift, shift_id)
            if not shift or shift.status != "OPEN":
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

    def close_shift(self, shift_id: int, counted_cash: Decimal) -> Dict[str, Any]:
        with self.db.get_session() as session:
            shift = session.get(Shift, shift_id)
            if not shift or shift.status != "OPEN":
                raise ValueError("Shift is not open or does not exist.")

            # Calculate totals
            # 1. Total Cash Sales
            cash_sales_stmt = (
                select(func.sum(SalePayment.amount))
                .join(Sale)
                .where(
                    Sale.cashier_id == shift.user_id,
                    Sale.timestamp >= shift.start_time,
                    SalePayment.payment_method == "Cash",
                )
            )
            total_cash_sales = session.scalar(cash_sales_stmt) or Decimal(0)

            # 2. Cash Movements (IN/OUT/DROP/PAYOUT)
            # Assuming IN adds to drawer, OUT/DROP/PAYOUT subtracts?
            # Usually:
            # IN = Add to drawer (e.g. buying change)
            # OUT = Remove from drawer (e.g. expense)
            # DROP = Remove to safe
            # PAYOUT = Remove to vendor/customer

            movements = session.scalars(
                select(CashMovement).where(CashMovement.shift_id == shift_id)
            ).all()

            total_drops = sum(m.amount for m in movements if m.type == "DROP")
            total_payouts = sum(
                m.amount for m in movements if m.type == "PAYOUT" or m.type == "OUT"
            )
            total_ins = sum(m.amount for m in movements if m.type == "IN")

            expected_cash = (
                shift.starting_cash
                + total_cash_sales
                + total_ins
                - total_drops
                - total_payouts
            )
            variance = counted_cash - expected_cash

            # Update Shift
            shift.end_time = datetime.now()
            shift.actual_cash = counted_cash
            shift.expected_cash = expected_cash
            shift.status = "CLOSED"

            session.commit()

            return {
                "shift_id": shift.id,
                "start_time": shift.start_time,
                "end_time": shift.end_time,
                "starting_cash": shift.starting_cash,
                "cash_sales": total_cash_sales,
                "cash_in": total_ins,
                "cash_out": total_payouts + total_drops,
                "expected_cash": expected_cash,
                "actual_cash": counted_cash,
                "variance": variance,
            }
