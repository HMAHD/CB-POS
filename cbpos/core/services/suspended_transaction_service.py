import json
import logging
from decimal import Decimal
from cbpos.core.database import Database
from cbpos.core.models import SuspendedTransaction
from cbpos.core.services.product_service import ProductService

logger = logging.getLogger(__name__)


class SuspendedTransactionService:
    """
    Service for managing suspended (held) transactions.
    Handles serialization, storage, and recall of held bills.
    """

    @staticmethod
    def hold_bill(cart_service, note: str = None) -> int | None:
        """Serialize cart items and save to SuspendedTransaction.

        The cart's attached customer (if any) is saved too, so recalling
        this bill later can restore it instead of always defaulting back
        to Walk-in Customer.

        Returns the suspended transaction ID on success, None on failure.
        """
        db = Database()
        try:
            with db.get_session() as session:
                # Serialize cart items
                items_data = []
                for item in cart_service.items:
                    items_data.append({"barcode": item["product"].barcode, "qty": str(item["qty"])})

                json_data = json.dumps(items_data)

                customer = cart_service.get_customer()
                suspended = SuspendedTransaction(
                    data=json_data, note=note, customer_id=customer.id if customer else None
                )
                session.add(suspended)
                session.flush()
                return suspended.id
        except Exception as e:
            logger.error("Hold Bill Failed: %s", e)
            return None

    @staticmethod
    def get_held_bills() -> list:
        """Return a list of all suspended transactions."""
        db = Database()
        with db.get_session() as session:
            suspended = session.query(SuspendedTransaction).order_by(SuspendedTransaction.timestamp.desc()).all()
            # Detach objects
            for s in suspended:
                session.expunge(s)
            return suspended

    @staticmethod
    def recall_bill(suspended_id: int, cart_service) -> bool:
        """Restore cart (and its attached customer, if any) from
        SuspendedTransaction and delete the record.

        The customer is restored before items are re-added so any
        customer-specific pricing applies the same way it did when the
        bill was held, not just visually re-attached afterward.
        """
        db = Database()
        try:
            with db.get_session() as session:
                suspended = session.get(SuspendedTransaction, suspended_id)
                if not suspended:
                    return False

                items_data = json.loads(suspended.data)
                customer_id = suspended.customer_id

                cart_service.clear()

                if customer_id:
                    from cbpos.core.services.customer_service import CustomerService

                    customer = CustomerService().get_customer(customer_id)
                    cart_service.set_customer(customer)

                for item in items_data:
                    product = ProductService.get_by_barcode(item["barcode"])
                    if product:
                        cart_service.add_item(product, Decimal(item["qty"]))

                session.delete(suspended)
            return True
        except Exception as e:
            logger.error("Recall Bill Failed: %s", e)
            return False

    @staticmethod
    def get_held_bill_count() -> int:
        """Return the number of currently held bills."""
        db = Database()
        with db.get_session() as session:
            return session.query(SuspendedTransaction).count()

    @staticmethod
    def get_latest_suspended() -> SuspendedTransaction:
        """Return the most recent suspended transaction, detached from session."""
        db = Database()
        with db.get_session() as session:
            suspended = session.query(SuspendedTransaction).order_by(SuspendedTransaction.timestamp.desc()).first()
            if suspended:
                session.expunge(suspended)
            return suspended
