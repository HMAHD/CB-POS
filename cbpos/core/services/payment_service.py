import logging
from typing import List, Optional

from cbpos.core.database import Database
from cbpos.core.models import PaymentMethod, SalePayment

logger = logging.getLogger(__name__)


class PaymentService:
    """Service to manage Payment Methods."""

    @staticmethod
    def get_all_methods() -> List[PaymentMethod]:
        """Get all payment methods."""
        db = Database()
        with db.get_session() as session:
            results = session.query(PaymentMethod).all()
            for m in results:
                session.expunge(m)
            return results

    @staticmethod
    def get_active_methods() -> List[PaymentMethod]:
        """Get only active payment methods."""
        db = Database()
        with db.get_session() as session:
            results = session.query(PaymentMethod).filter(PaymentMethod.is_active.is_(True)).all()
            for m in results:
                session.expunge(m)
            return results

    @staticmethod
    def create_method(
        name: str,
        is_cash: bool = False,
        open_drawer: bool = False,
        shortcut: Optional[str] = None,
    ) -> PaymentMethod:
        """Create a new payment method.

        Args:
            name: Display name (must be non-empty and unique among active methods).
            is_cash: Whether this method represents cash.
            open_drawer: Whether to kick the cash drawer on this method.
            shortcut: Optional keyboard shortcut key.

        Returns:
            The newly created PaymentMethod.

        Raises:
            ValueError: If name is empty or already exists.
        """
        if not name or not name.strip():
            raise ValueError("Payment method name cannot be empty")

        db = Database()
        with db.get_session() as session:
            existing = session.query(PaymentMethod).filter(PaymentMethod.name == name.strip()).first()
            if existing:
                raise ValueError("Payment method '{0}' already exists".format(name.strip()))

            method = PaymentMethod(
                name=name.strip(),
                is_cash=is_cash,
                open_drawer=open_drawer,
                shortcut=shortcut,
                is_active=True,
            )
            session.add(method)
            session.commit()
            session.refresh(method)
            session.expunge(method)
            logger.info("Created payment method: %s (id=%d)", method.name, method.id)
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
        """Update an existing payment method.

        Args:
            method_id: ID of the method to update.
            name: New name (must be unique if provided).
            is_cash: New cash flag.
            open_drawer: New drawer flag.
            shortcut: New shortcut key.
            is_active: New active flag.

        Returns:
            The updated PaymentMethod, or None if not found.

        Raises:
            ValueError: If new name conflicts with another method.
        """
        db = Database()
        with db.get_session() as session:
            method = session.get(PaymentMethod, method_id)
            if not method:
                logger.warning("Payment method id=%d not found for update", method_id)
                return None

            if name is not None:
                name = name.strip()
                if not name:
                    raise ValueError("Payment method name cannot be empty")
                conflict = (
                    session.query(PaymentMethod)
                    .filter(
                        PaymentMethod.name == name,
                        PaymentMethod.id != method_id,
                    )
                    .first()
                )
                if conflict:
                    raise ValueError("Payment method '{0}' already exists".format(name))
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
            session.expunge(method)
            logger.info("Updated payment method: %s (id=%d)", method.name, method.id)
            return method

    @staticmethod
    def delete_method(method_id: int) -> bool:
        """Delete a payment method if it has no associated sales.

        Methods that have been used in completed sales are deactivated instead
        of deleted to preserve referential integrity.

        Args:
            method_id: ID of the method to delete.

        Returns:
            True if deleted or deactivated, False if not found.
        """
        db = Database()
        with db.get_session() as session:
            method = session.get(PaymentMethod, method_id)
            if not method:
                logger.warning("Payment method id=%d not found for deletion", method_id)
                return False

            # Check if method is referenced by any sale payments
            has_sales = (
                session.query(SalePayment).filter(SalePayment.payment_method == method.name).first()
            ) is not None

            if has_sales:
                # Deactivate instead of deleting to preserve history
                method.is_active = False
                session.commit()
                logger.info(
                    "Deactivated payment method '%s' (id=%d) — has existing sales",
                    method.name,
                    method.id,
                )
            else:
                session.delete(method)
                session.commit()
                logger.info("Deleted payment method '%s' (id=%d)", method.name, method.id)
            return True
