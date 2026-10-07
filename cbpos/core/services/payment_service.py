import logging

from cbpos.core.database import Database
from cbpos.core.models import PaymentMethod, SalePayment

logger = logging.getLogger(__name__)

# Keys PaymentDialog already binds: Enter/Return add a payment, F12 is
# quick-pay cash, Esc is QDialog's built-in cancel. A method shortcut on
# any of these makes Qt's shortcut ambiguous and neither one fires (#640).
RESERVED_SHORTCUTS = frozenset({"return", "enter", "f12", "esc"})


def normalize_shortcut(shortcut: str | None) -> str:
    """Return a case-insensitive comparison key for a stored shortcut.

    Drops Qt's keypad modifier ("Num+Enter" fires the same as "Enter") and
    folds "Escape" to Qt's portable "Esc".

    Args:
        shortcut: Stored shortcut text such as "F1" or "Ctrl+F5".

    Returns:
        Normalized key, or "" when there is no shortcut.
    """
    if not shortcut:
        return ""
    parts = [p.strip().casefold() for p in shortcut.split("+")]
    parts = ["esc" if p == "escape" else p for p in parts if p and p != "num"]
    return "+".join(parts)


class ShortcutConflictError(ValueError):
    """A payment method shortcut collides with a reserved key or another active method.

    Attributes:
        shortcut: The rejected shortcut text.
        conflict_with: Name of the active method already using it, or None
            when the key is reserved by the payment dialog itself.
    """

    def __init__(self, shortcut: str, conflict_with: str | None = None):
        self.shortcut = shortcut
        self.conflict_with = conflict_with
        if conflict_with is None:
            msg = f"Shortcut '{shortcut}' is reserved by the payment screen"
        else:
            msg = f"Shortcut '{shortcut}' is already used by '{conflict_with}'"
        super().__init__(msg)


class PaymentService:
    """Service to manage Payment Methods."""

    @staticmethod
    def _check_shortcut(session, shortcut: str | None, exclude_id: int | None, check_reserved: bool) -> None:
        """Raise ShortcutConflictError if `shortcut` can't be used by an active method.

        Args:
            session: Open DB session.
            shortcut: Shortcut to check; empty means none, which never conflicts.
            exclude_id: The method being edited, so it doesn't clash with itself.
            check_reserved: Whether to also reject the payment dialog's own keys.
        """
        key = normalize_shortcut(shortcut)
        if not key:
            return
        if check_reserved and key in RESERVED_SHORTCUTS:
            raise ShortcutConflictError(shortcut)
        query = session.query(PaymentMethod).filter(
            PaymentMethod.is_active.is_(True), PaymentMethod.shortcut.isnot(None)
        )
        if exclude_id is not None:
            query = query.filter(PaymentMethod.id != exclude_id)
        for other in query.all():
            if normalize_shortcut(other.shortcut) == key:
                raise ShortcutConflictError(shortcut, other.name)

    @staticmethod
    def validate_shortcut(shortcut: str | None, exclude_id: int | None = None, active: bool = True) -> None:
        """Check a shortcut before saving: not reserved, and unique among active methods.

        Args:
            shortcut: Shortcut text such as "F5"; empty or None means no shortcut.
            exclude_id: ID of the method being edited, if any.
            active: Whether the method will be active; inactive methods may share keys.

        Raises:
            ShortcutConflictError: If the key is reserved or already used.
        """
        if normalize_shortcut(shortcut) in RESERVED_SHORTCUTS:
            raise ShortcutConflictError(shortcut)
        if not active:
            return
        db = Database()
        with db.get_session() as session:
            PaymentService._check_shortcut(session, shortcut, exclude_id, check_reserved=False)

    @staticmethod
    def get_all_methods() -> list[PaymentMethod]:
        """Get all payment methods."""
        db = Database()
        with db.get_session() as session:
            results = session.query(PaymentMethod).all()
            for m in results:
                session.expunge(m)
            return results

    @staticmethod
    def get_active_methods() -> list[PaymentMethod]:
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
        shortcut: str | None = None,
    ) -> PaymentMethod:
        """Create a new payment method.

        Args:
            name: Display name (must be non-empty and unique among active methods).
            is_cash: Whether this method represents cash.
            open_drawer: Whether to kick the cash drawer on this method.
            shortcut: Optional keyboard shortcut key; empty means none.

        Returns:
            The newly created PaymentMethod.

        Raises:
            ValueError: If name is empty or already exists.
            ShortcutConflictError: If the shortcut is reserved or used by another active method.
        """
        shortcut = (shortcut or "").strip() or None
        if not name or not name.strip():
            raise ValueError("Payment method name cannot be empty")

        db = Database()
        with db.get_session() as session:
            existing = session.query(PaymentMethod).filter(PaymentMethod.name == name.strip()).first()
            if existing:
                raise ValueError(f"Payment method '{name.strip()}' already exists")
            PaymentService._check_shortcut(session, shortcut, None, check_reserved=True)

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
        name: str | None = None,
        is_cash: bool | None = None,
        open_drawer: bool | None = None,
        shortcut: str | None = None,
        is_active: bool | None = None,
    ) -> PaymentMethod | None:
        """Update an existing payment method.

        Args:
            method_id: ID of the method to update.
            name: New name (must be unique if provided).
            is_cash: New cash flag.
            open_drawer: New drawer flag.
            shortcut: New shortcut key; "" clears it, None leaves it unchanged.
            is_active: New active flag.

        Returns:
            The updated PaymentMethod, or None if not found.

        Raises:
            ValueError: If new name conflicts with another method.
            ShortcutConflictError: If the shortcut is reserved, or the method would
                end up active sharing a key with another active method.
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
                    raise ValueError(f"Payment method '{name}' already exists")
                method.name = name
            if is_cash is not None:
                method.is_cash = is_cash
            if open_drawer is not None:
                method.open_drawer = open_drawer
            if shortcut is not None:
                shortcut = shortcut.strip() or None
                if normalize_shortcut(shortcut) in RESERVED_SHORTCUTS:
                    raise ShortcutConflictError(shortcut)
                method.shortcut = shortcut
            if is_active is not None:
                method.is_active = is_active
            # Re-keying or activating a method must not leave two active
            # methods on one key. Inactive methods may share keys. Reserved
            # keys are only checked above when the shortcut itself changes,
            # so an old DB row (e.g. Cash on F12) can still be toggled.
            if method.is_active and (shortcut is not None or is_active):
                PaymentService._check_shortcut(session, method.shortcut, method_id, check_reserved=False)

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
