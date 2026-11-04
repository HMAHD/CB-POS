import logging

from sqlalchemy import func, select, union
from sqlalchemy.orm import Session

from cbpos.core.constants.status import PaymentMethodKind
from cbpos.core.database import Database
from cbpos.core.models import CustomerPayment, PaymentMethod, Sale, SalePayment, SupplierPayment
from cbpos.core.utils.terminal_guard import require_catalog_writable

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


BUILTIN_METHOD_NAMES = frozenset(
    {
        "cash",
        "card",
        "credit",
        "qr/mobile",
        "cheque",
        "bank transfer",
        "transfer",
    }
)


def classify_method_name(name: str | None) -> str:
    """Classify a raw payment method display name to a PaymentMethodKind.

    Case-insensitive matching:
    - 'cash' -> CASH
    - 'card' -> CARD
    - 'credit' -> CREDIT
    - 'qr/mobile', 'qr', 'mobile' -> QR
    - 'cheque', 'check' -> CHEQUE
    - 'transfer', 'bank transfer' -> TRANSFER
    - 'refund' -> REFUND_LEGACY
    - otherwise -> OTHER
    """
    if not name:
        return PaymentMethodKind.OTHER
    cleaned = name.strip().lower()
    if cleaned == "cash":
        return PaymentMethodKind.CASH
    if cleaned == "card":
        return PaymentMethodKind.CARD
    if cleaned == "credit":
        return PaymentMethodKind.CREDIT
    if cleaned in ("qr/mobile", "qr", "mobile"):
        return PaymentMethodKind.QR
    if cleaned in ("cheque", "check"):
        return PaymentMethodKind.CHEQUE
    if cleaned in ("transfer", "bank transfer"):
        return PaymentMethodKind.TRANSFER
    if cleaned == "refund":
        return PaymentMethodKind.REFUND_LEGACY
    return PaymentMethodKind.OTHER


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


class PaymentMethodInUseError(ValueError):
    """A payment method already used in past payments can't be renamed (#639).

    Payments store the method *name* as text, so a rename would orphan the
    old rows from the method: reports split, and the "has history" delete
    protection would no longer see them.

    Attributes:
        name: The method's current (locked) name.
    """

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Payment method '{name}' is used in past payments and can't be renamed")


# Every column that stores a payment method by name.
_PAYMENT_NAME_COLUMNS = (
    SalePayment.payment_method,
    Sale.payment_method,
    CustomerPayment.payment_method,
    SupplierPayment.payment_method,
)


class PaymentService:
    """Service to manage Payment Methods."""

    @staticmethod
    def _used_names(session: Session) -> set[str]:
        """Casefolded names of every method that appears on a recorded payment.

        Args:
            session: Open DB session.

        Returns:
            Set of lower-cased method names found in payment history.
        """
        stmt = union(*(select(func.lower(column)).distinct() for column in _PAYMENT_NAME_COLUMNS))
        return {name for name in session.scalars(stmt) if name}

    @staticmethod
    def _name_is_used(session: Session, name: str) -> bool:
        """Whether any recorded payment (sale, credit book, supplier) uses ``name``.

        Matched case-insensitively, as checkout compares methods that way.

        Args:
            session: Open DB session.
            name: Method name to look for.

        Returns:
            True if the name appears in payment history.
        """
        key = name.lower()
        return any(
            session.scalar(select(column).where(func.lower(column) == key).limit(1)) is not None
            for column in _PAYMENT_NAME_COLUMNS
        )

    @staticmethod
    def is_method_used(method_id: int) -> bool:
        """Whether a payment method has payment history (so it can't be renamed or deleted).

        Args:
            method_id: ID of the method.

        Returns:
            True if past payments reference the method; False if it has none or doesn't exist.
        """
        db = Database()
        with db.get_session() as session:
            method = session.get(PaymentMethod, method_id)
            return method is not None and PaymentService._name_is_used(session, method.name)

    @staticmethod
    def get_used_method_ids() -> set[int]:
        """IDs of all payment methods that have payment history.

        Returns:
            Set of method IDs whose name appears on a recorded payment.
        """
        db = Database()
        with db.get_session() as session:
            used = PaymentService._used_names(session)
            return {m.id for m in session.query(PaymentMethod).all() if m.name.lower() in used}

    @staticmethod
    def _check_shortcut(session: Session, shortcut: str | None, exclude_id: int | None, check_reserved: bool) -> None:
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
    def get_kind_for(method_name: str, session: Session | None = None) -> str:
        """Resolve PaymentMethodKind for a method name.

        Looks up the PaymentMethod in DB by name (case-insensitive);
        if not found, classifies the name using classify_method_name.
        """
        if not method_name:
            return PaymentMethodKind.OTHER

        def _lookup(s: Session) -> str | None:
            m = s.query(PaymentMethod).filter(func.lower(PaymentMethod.name) == method_name.strip().lower()).first()
            return m.kind if m else None

        if session is not None:
            kind = _lookup(session)
            if kind:
                return kind
        else:
            db = Database()
            with db.get_session() as s:
                kind = _lookup(s)
                if kind:
                    return kind

        return classify_method_name(method_name)

    @staticmethod
    def get_default_cash_method() -> PaymentMethod | None:
        """Get the default active cash payment method (first active with kind CASH, ordered by id)."""
        db = Database()
        with db.get_session() as session:
            method = (
                session.query(PaymentMethod)
                .filter(
                    PaymentMethod.is_active.is_(True),
                    PaymentMethod.kind == PaymentMethodKind.CASH,
                )
                .order_by(PaymentMethod.id.asc())
                .first()
            )
            if method:
                session.expunge(method)
            return method

    @staticmethod
    def is_builtin_method(method: PaymentMethod | None) -> bool:
        """Whether a payment method is a built-in method whose type cannot be changed."""
        if not method:
            return False
        if method.name and method.name.strip().casefold() in BUILTIN_METHOD_NAMES:
            return True
        return bool(method.id and method.id <= 6)

    @staticmethod
    def create_method(
        name: str,
        is_cash: bool = False,
        open_drawer: bool = False,
        shortcut: str | None = None,
        kind: str | None = None,
    ) -> PaymentMethod:
        """Create a new payment method.

        Args:
            name: Display name (must be non-empty and unique among active methods).
            is_cash: Whether this method represents cash (kept in sync with kind).
            open_drawer: Whether to kick the cash drawer on this method.
            shortcut: Optional keyboard shortcut key; empty means none.
            kind: Optional stable PaymentMethodKind; defaults to CASH if is_cash else derived.

        Returns:
            The newly created PaymentMethod.

        Raises:
            ValueError: If name is empty or already exists.
            ShortcutConflictError: If the shortcut is reserved or used by another active method.
        """
        require_catalog_writable()
        shortcut = (shortcut or "").strip() or None
        if not name or not name.strip():
            raise ValueError("Payment method name cannot be empty")

        if kind is None:
            kind = PaymentMethodKind.CASH if is_cash else classify_method_name(name)
        is_cash = kind == PaymentMethodKind.CASH

        db = Database()
        with db.get_session() as session:
            existing = session.query(PaymentMethod).filter(PaymentMethod.name == name.strip()).first()
            if existing:
                raise ValueError(f"Payment method '{name.strip()}' already exists")
            PaymentService._check_shortcut(session, shortcut, None, check_reserved=True)

            method = PaymentMethod(
                name=name.strip(),
                kind=kind,
                is_cash=is_cash,
                open_drawer=open_drawer,
                shortcut=shortcut,
                is_active=True,
            )
            session.add(method)
            session.commit()
            session.refresh(method)
            session.expunge(method)
            logger.info("Created payment method: %s (id=%d, kind=%s)", method.name, method.id, method.kind)
            return method

    @staticmethod
    def update_method(
        method_id: int,
        name: str | None = None,
        is_cash: bool | None = None,
        open_drawer: bool | None = None,
        shortcut: str | None = None,
        is_active: bool | None = None,
        kind: str | None = None,
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
            PaymentMethodInUseError: If the name changes on a method that past
                payments already use (#639).
            ShortcutConflictError: If the shortcut is reserved, or the method would
                end up active sharing a key with another active method.
        """
        require_catalog_writable()
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
                if name != method.name and PaymentService._name_is_used(session, method.name):
                    raise PaymentMethodInUseError(method.name)
                method.name = name
            if kind is not None:
                method.kind = kind
                method.is_cash = kind == PaymentMethodKind.CASH
            elif is_cash is not None:
                method.is_cash = is_cash
                if is_cash:
                    method.kind = PaymentMethodKind.CASH
                elif method.kind == PaymentMethodKind.CASH:
                    method.kind = PaymentMethodKind.OTHER
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
        """Delete a payment method if it has no payment history.

        Methods that have been used (sales, credit book or supplier payments)
        are deactivated instead of deleted to preserve history. A used method
        can't be renamed (#639), so its name always still matches its history.

        Args:
            method_id: ID of the method to delete.

        Returns:
            True if deleted or deactivated, False if not found.
        """
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            method = session.get(PaymentMethod, method_id)
            if not method:
                logger.warning("Payment method id=%d not found for deletion", method_id)
                return False

            if PaymentService._name_is_used(session, method.name):
                # Deactivate instead of deleting to preserve history
                method.is_active = False
                session.commit()
                logger.info(
                    "Deactivated payment method '%s' (id=%d) — has payment history",
                    method.name,
                    method.id,
                )
            else:
                session.delete(method)
                session.commit()
                logger.info("Deleted payment method '%s' (id=%d)", method.name, method.id)
            return True
