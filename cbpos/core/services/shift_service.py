from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy import select, func
from cbpos.core.database import Database
from cbpos.core.models import Shift, CashMovement, Sale, SalePayment
from cbpos.core.constants.status import ShiftStatus, DocumentStatus, PaymentMethodType


class ShiftService:
    def __init__(self):
        self.db = Database()

    def start_shift(self, user_id: int, float_amount: Decimal) -> Shift:
        with self.db.get_session() as session:
            # Check if user already has an open shift
            existing_shift = session.scalars(
                select(Shift).where(Shift.user_id == user_id, Shift.status == ShiftStatus.OPEN)
            ).first()

            if existing_shift:
                raise ValueError("User already has an open shift.")

            shift = Shift(
                user_id=user_id,
                starting_cash=float_amount,
                start_time=datetime.now(),
                status=ShiftStatus.OPEN,
            )
            session.add(shift)
            session.commit()
            session.refresh(shift)
            return shift

    def get_current_shift(self, user_id: int) -> Optional[Shift]:
        with self.db.get_session() as session:
            return session.scalars(
                select(Shift).where(Shift.user_id == user_id, Shift.status == ShiftStatus.OPEN)
            ).first()

    def record_cash_movement(
        self, shift_id: int, type: str, amount: Decimal, reason: str, user_id: int
    ) -> CashMovement:
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

    def get_shift_summary(self, shift_id: int) -> Dict[str, Any]:
        with self.db.get_session() as session:
            shift = session.get(Shift, shift_id)
            if not shift:
                raise ValueError("Shift does not exist.")

            # 1. Sales Breakdown by Payment Method
            sales_stmt = (
                select(
                    SalePayment.payment_method,
                    func.sum(SalePayment.amount).label("total"),
                )
                .join(Sale)
                .where(
                    Sale.user_id == shift.user_id,
                    Sale.date >= shift.start_time,
                    Sale.status == DocumentStatus.COMPLETED,
                )
            )
            if shift.end_time:
                sales_stmt = sales_stmt.where(Sale.date <= shift.end_time)

            sales_stmt = sales_stmt.group_by(SalePayment.payment_method)
            sales_results = session.execute(sales_stmt).all()
            sales_by_method = {row[0]: row[1] for row in sales_results}

            total_cash_sales = sales_by_method.get(PaymentMethodType.CASH, Decimal(0))
            total_card_sales = sales_by_method.get(PaymentMethodType.CARD, Decimal(0))
            total_credit_sales = sales_by_method.get(PaymentMethodType.CREDIT, Decimal(0))
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
                Sale.user_id == shift.user_id,
                Sale.date >= shift.start_time,
                Sale.status == DocumentStatus.VOID,
            )
            if shift.end_time:
                void_stmt = void_stmt.where(Sale.date <= shift.end_time)
            void_count, void_value = session.execute(void_stmt).first()

            # Transaction Count
            txn_stmt = select(func.count(Sale.id)).where(
                Sale.user_id == shift.user_id,
                Sale.date >= shift.start_time,
                Sale.status == DocumentStatus.COMPLETED,
            )
            if shift.end_time:
                txn_stmt = txn_stmt.where(Sale.date <= shift.end_time)
            txn_count = session.scalar(txn_stmt)

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
                "cash_in": total_ins,
                "cash_out": total_payouts + total_drops,
                "expected_cash": expected_cash,
                "void_count": void_count or 0,
                "void_value": void_value or Decimal(0),
                "txn_count": txn_count or 0,
            }

    def close_shift(self, shift_id: int, counted_cash: Decimal, notes: str = None) -> Dict[str, Any]:
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
            # We might want to store notes/variance in the shift model if we add those fields later
            # For now, we rely on the calculated values

            session.commit()

            # Return full summary with closing details
            summary["end_time"] = shift.end_time
            summary["actual_cash"] = counted_cash
            summary["variance"] = variance
            summary["notes"] = notes

            return summary
