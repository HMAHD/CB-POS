import json
import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from cbpos.core.database import Database
from cbpos.core.models import Product, SuspendedTransaction
from cbpos.core.services.pricing_service import PricingService
from cbpos.core.services.product_service import ProductService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


@dataclass
class RecallResult:
    """Result of recalling a suspended bill, including success status and notices."""

    ok: bool
    notices: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


class SuspendedTransactionService:
    """
    Service for managing suspended (held) transactions.
    Handles serialization, storage, and recall of held bills.
    """

    @staticmethod
    def hold_bill(cart_service, note: str = None) -> int | None:
        """Serialize cart items and save to SuspendedTransaction (v2 format).

        Preserves line discounts, price overrides, notes, cart discounts,
        and customer.

        Returns the suspended transaction ID on success, None on failure.
        """
        db = Database()
        try:
            with db.get_session() as session:
                lines_data = []
                for item in cart_service.items:
                    lines_data.append(
                        {
                            "product_id": item["product"].id,
                            "barcode": item["product"].barcode,
                            "qty": str(item["qty"]),
                            "unit_price": str(item["unit_price"]),
                            "original_price": str(item["original_price"]),
                            "is_manual_price": bool(item.get("is_manual_price", False)),
                            "override_approved_by": item.get("override_approved_by"),
                            "discount_type": item.get("discount_type", "NONE"),
                            "discount_value": str(item.get("discount_value", Decimal("0.00"))),
                            "notes": item.get("note") or item.get("notes") or "",
                        }
                    )

                cart_data = {
                    "discount_type": cart_service.cart_discount_type,
                    "discount_value": str(cart_service.cart_discount_value),
                }

                payload = {
                    "v": 2,
                    "cart": cart_data,
                    "lines": lines_data,
                }
                json_data = json.dumps(payload)

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
    def recall_bill(suspended_id: int, cart_service) -> RecallResult:
        """Restore cart (and its attached customer, if any) from
        SuspendedTransaction and delete the record.

        Supports both v2 (with overrides, discounts, notes, notices)
        and legacy v1 held bills.
        """
        db = Database()
        try:
            with db.get_session() as session:
                suspended = session.get(SuspendedTransaction, suspended_id)
                if not suspended:
                    return RecallResult(ok=False)

                payload = json.loads(suspended.data)
                customer_id = suspended.customer_id
                notices: list[str] = []

                cart_service.clear()

                customer = None
                if customer_id:
                    from cbpos.core.services.customer_service import CustomerService

                    customer = CustomerService().get_customer(customer_id)
                    cart_service.set_customer(customer)

                if isinstance(payload, dict) and payload.get("v") == 2:
                    # v2 format
                    lines = payload.get("lines", [])
                    for line in lines:
                        product_id = line.get("product_id")
                        barcode = line.get("barcode")
                        product = None
                        if product_id:
                            product = session.get(Product, product_id)
                        if (not product or not product.is_active) and barcode:
                            product = ProductService.get_by_barcode(barcode)

                        if not product or not product.is_active:
                            name = (product.name_en if product else None) or barcode or f"Item #{product_id}"
                            notices.append(_t("orders.recall_item_missing", name=name))
                            continue

                        qty = Decimal(str(line.get("qty", "1.000"))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                        cart_service.add_item(product, qty)
                        line_idx = len(cart_service.items) - 1

                        held_orig = Decimal(str(line.get("original_price", product.price)))
                        held_unit = Decimal(str(line.get("unit_price", product.price)))

                        # Check if product's current base price changed
                        current_pricing = PricingService.calculate_price(product, customer)
                        current_orig = current_pricing["original_price"]
                        if current_orig != held_orig:
                            notices.append(
                                _t(
                                    "orders.recall_price_changed",
                                    name=product.name_en,
                                    new=format_currency(current_orig),
                                    old=format_currency(held_orig),
                                )
                            )

                        if line.get("is_manual_price"):
                            cart_service.restore_line_override(
                                line_idx, held_unit, approved_by=line.get("override_approved_by")
                            )
                        elif held_unit != cart_service.items[line_idx]["unit_price"]:
                            cart_service.items[line_idx]["unit_price"] = held_unit
                            cart_service.items[line_idx]["original_price"] = held_orig
                            cart_service._recalculate_line(cart_service.items[line_idx])

                        # Restore discount
                        disc_type = line.get("discount_type", "NONE")
                        disc_val = Decimal(str(line.get("discount_value", "0.00")))
                        if disc_type != "NONE" and disc_val > Decimal("0.00"):
                            cart_service.restore_line_discount(line_idx, disc_type, disc_val)

                        # Restore note
                        note = line.get("notes") or line.get("note")
                        if note:
                            cart_service.set_line_note(line_idx, note)

                    # Restore cart discount
                    cart_info = payload.get("cart", {})
                    cart_disc_type = cart_info.get("discount_type", "NONE")
                    cart_disc_val = Decimal(str(cart_info.get("discount_value", "0.00")))
                    if cart_disc_type != "NONE" and cart_disc_val > Decimal("0.00"):
                        cart_service.restore_cart_discount(cart_disc_type, cart_disc_val)

                else:
                    # Legacy v1 format (list of dicts)
                    items_data = payload if isinstance(payload, list) else []
                    for item in items_data:
                        product = ProductService.get_by_barcode(item["barcode"])
                        if product and product.is_active:
                            cart_service.add_item(
                                product,
                                Decimal(str(item["qty"])).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                            )
                        elif product and not product.is_active:
                            notices.append(_t("orders.recall_item_missing", name=product.name_en))
                        else:
                            notices.append(_t("orders.recall_item_missing", name=item.get("barcode", "Unknown")))

                session.delete(suspended)
            return RecallResult(ok=True, notices=notices)
        except Exception as e:
            logger.error("Recall Bill Failed: %s", e)
            return RecallResult(ok=False)

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
