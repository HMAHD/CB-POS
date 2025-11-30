from typing import List, Optional
from cbpos.core.database import Database
from cbpos.core.models import PaymentMethod


class PaymentService:
    """
    Service to manage Payment Methods.
    """

    @staticmethod
    def get_all_methods() -> List[PaymentMethod]:
        """
        Get all payment methods.
        """
        db = Database()
        with db.get_session() as session:
            return session.query(PaymentMethod).all()

    @staticmethod
    def get_active_methods() -> List[PaymentMethod]:
        """
        Get only active payment methods.
        """
        db = Database()
        with db.get_session() as session:
            return (
                session.query(PaymentMethod)
                .filter(PaymentMethod.is_active.is_(True))
                .all()
            )

    @staticmethod
    def create_method(
        name: str,
        is_cash: bool = False,
        open_drawer: bool = False,
        shortcut: Optional[str] = None,
    ) -> PaymentMethod:
        """
        Create a new payment method.
        """
        db = Database()
        with db.get_session() as session:
            method = PaymentMethod(
                name=name,
                is_cash=is_cash,
                open_drawer=open_drawer,
                shortcut=shortcut,
                is_active=True,
            )
            session.add(method)
            session.commit()
            session.refresh(method)
            return method

    @staticmethod
    def update_method(
        method_id: int,
        name: Optional[str] = None,
        is_cash: Optional[bool] = None,
        open_drawer: Optional[bool] = None,
        shortcut: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[PaymentMethod]:
        """
        Update an existing payment method.
        """
        db = Database()
        with db.get_session() as session:
            method = session.query(PaymentMethod).get(method_id)
            if not method:
                return None

            if name is not None:
                method.name = name
            if is_cash is not None:
                method.is_cash = is_cash
            if open_drawer is not None:
                method.open_drawer = open_drawer
            if shortcut is not None:
                method.shortcut = shortcut
            if is_active is not None:
                method.is_active = is_active

            session.commit()
            session.refresh(method)
            return method

    @staticmethod
    def delete_method(method_id: int) -> bool:
        """
        Delete (or deactivate) a payment method.
        Actually deletes from DB if no dependencies, otherwise handle gracefully.
        For now, we'll just delete.
        """
        db = Database()
        with db.get_session() as session:
            method = session.query(PaymentMethod).get(method_id)
            if method:
                session.delete(method)
                session.commit()
                return True
            return False
