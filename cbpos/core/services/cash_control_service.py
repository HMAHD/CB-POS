from datetime import datetime
from decimal import Decimal
from typing import Optional

from cbpos.core.database import Database
from cbpos.core.models import Shift, CashMovement


class CashControlService:
    @staticmethod
    def start_shift(user_id: int, start_float: Decimal) -> Optional[Shift]:
        db = Database()
        with db.get_session() as session:
            # Check if user already has an open shift
            existing = session.query(Shift).filter_by(user_id=user_id, status="OPEN").first()
            if existing:
                return None  # Shift already open

            shift = Shift(
                user_id=user_id,
                start_time=datetime.now(),
                start_float=start_float,
                status="OPEN",
            )
            session.add(shift)
            session.commit()
            session.refresh(shift)
            session.expunge(shift)
            return shift

    @staticmethod
    def end_shift(user_id: int, end_cash: Decimal) -> Optional[Shift]:
        db = Database()
        with db.get_session() as session:
            shift = session.query(Shift).filter_by(user_id=user_id, status="OPEN").first()
            if not shift:
                return None

            shift.end_time = datetime.now()
            shift.end_cash = end_cash
            shift.status = "CLOSED"
            session.commit()
            session.refresh(shift)
            session.expunge(shift)
            return shift

    @staticmethod
    def get_current_shift(user_id: int) -> Optional[Shift]:
        db = Database()
        with db.get_session() as session:
            shift = session.query(Shift).filter_by(user_id=user_id, status="OPEN").first()
            if shift:
                session.expunge(shift)
            return shift

    @staticmethod
    def record_cash_in(user_id: int, amount: Decimal, reason: str) -> bool:
        return CashControlService._record_movement(user_id, "IN", amount, reason)

    @staticmethod
    def record_cash_out(user_id: int, amount: Decimal, reason: str) -> bool:
        return CashControlService._record_movement(user_id, "OUT", amount, reason)

    @staticmethod
    def _record_movement(user_id: int, type_: str, amount: Decimal, reason: str) -> bool:
        db = Database()
        with db.get_session() as session:
            shift = session.query(Shift).filter_by(user_id=user_id, status="OPEN").first()

            movement = CashMovement(
                shift_id=shift.id if shift else None,
                user_id=user_id,
                type=type_,
                amount=amount,
                reason=reason,
                timestamp=datetime.now(),
            )
            session.add(movement)
            session.commit()
            return True
