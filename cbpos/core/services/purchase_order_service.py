from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import Product, PurchaseOrder, PurchaseOrderItem
from cbpos.core.services.document_service import DocumentService


class PurchaseOrderService:
    """Manages Purchase Orders: persisted, receivable independently of any
    single GRN so an order can be received in full or across several
    partial GRNs over time (#486)."""

    @staticmethod
    def create_purchase_order(supplier_id: int, user_id: int, items: list[dict[str, Any]]) -> PurchaseOrder:
        """Create a Purchase Order with its line items.

        items format: [{'product_id': int, 'qty_ordered': Decimal}]
        """
        document_number = DocumentService.generate_number("PURCHASE_ORDER")

        db = Database()
        with db.get_session() as session:
            order = PurchaseOrder(
                document_number=document_number,
                type="purchase_order",
                date=datetime.now(),
                user_id=user_id,
                status="ORDERED",
                supplier_id=supplier_id,
            )
            session.add(order)
            session.flush()

            for item in items:
                session.add(
                    PurchaseOrderItem(
                        purchase_order_id=order.id,
                        product_id=item["product_id"],
                        qty_ordered=item["qty_ordered"],
                        qty_received=Decimal("0"),
                    )
                )

            session.commit()
            session.refresh(order)
            return order

    @staticmethod
    def get_open_orders(supplier_id: int | None = None) -> list[PurchaseOrder]:
        """List orders still awaiting full receipt (ORDERED or PARTIALLY_RECEIVED)."""
        db = Database()
        with db.get_session() as session:
            query = (
                session.query(PurchaseOrder)
                .options(
                    joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.product),
                    joinedload(PurchaseOrder.supplier),
                )
                .filter(PurchaseOrder.status.in_(["ORDERED", "PARTIALLY_RECEIVED"]))
            )
            if supplier_id:
                query = query.filter(PurchaseOrder.supplier_id == supplier_id)
            orders = query.order_by(PurchaseOrder.date.desc()).all()
            for order in orders:
                session.expunge(order)
            return orders

    @staticmethod
    def get_order(order_id: int) -> PurchaseOrder | None:
        """Fetch a single Purchase Order with items, products, and supplier eager-loaded."""
        db = Database()
        with db.get_session() as session:
            order = (
                session.query(PurchaseOrder)
                .options(
                    joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.product),
                    joinedload(PurchaseOrder.supplier),
                )
                .filter_by(id=order_id)
                .first()
            )
            if order:
                session.expunge(order)
            return order

    @staticmethod
    def check_receipt_discrepancies(order_id: int, items_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compare a GRN against what is still outstanding on a Purchase Order.

        Outstanding is ``qty_ordered - qty_received`` so far, so earlier
        partial GRNs are taken into account. GRN lines for the same product
        are summed. This only reports differences for the caller to confirm
        with the cashier; partial deliveries are valid, so nothing here
        blocks a receipt (#486, #719).

        Args:
            order_id: The Purchase Order the GRN is received against.
            items_data: GRN lines, ``[{'product_id': int, 'qty': Decimal, ...}]``.

        Returns:
            One dict per mismatch, GRN lines first (in GRN order), then
            order lines missing from the GRN (in order-line order)::

                {
                    "kind": "over" | "under" | "not_on_order" | "not_received",
                    "product_id": int,
                    "product_name": str,   # Product.get_display_name(), UI language
                    "outstanding": Decimal,  # 0 for "not_on_order"
                    "received": Decimal,     # 0 for "not_received"
                    "decimal_places": int,   # for format_quantity
                }

            An unknown order, or a GRN that exactly matches every
            outstanding line, gives an empty list.
        """
        received_by_product: dict[int, Decimal] = {}
        for data in items_data:
            product_id = int(data["product_id"])
            qty = Decimal(str(data["qty"]))
            received_by_product[product_id] = received_by_product.get(product_id, Decimal("0")) + qty

        db = Database()
        with db.get_session() as session:
            order = (
                session.query(PurchaseOrder)
                .options(joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.product))
                .filter_by(id=order_id)
                .first()
            )
            if not order:
                return []

            order_items_by_product = {item.product_id: item for item in order.items}
            unordered_ids = [pid for pid in received_by_product if pid not in order_items_by_product]
            unordered_products = (
                {p.id: p for p in session.query(Product).filter(Product.id.in_(unordered_ids)).all()}
                if unordered_ids
                else {}
            )

            discrepancies: list[dict[str, Any]] = []
            for product_id, received in received_by_product.items():
                order_item = order_items_by_product.get(product_id)
                if order_item is None:
                    product = unordered_products.get(product_id)
                    if product is None:
                        continue
                    discrepancies.append(
                        PurchaseOrderService._discrepancy("not_on_order", product, Decimal("0"), received)
                    )
                    continue
                outstanding = order_item.qty_ordered - order_item.qty_received
                if received != outstanding:
                    kind = "over" if received > outstanding else "under"
                    discrepancies.append(
                        PurchaseOrderService._discrepancy(kind, order_item.product, outstanding, received)
                    )

            for order_item in order.items:
                if order_item.product_id in received_by_product:
                    continue
                outstanding = order_item.qty_ordered - order_item.qty_received
                if outstanding > 0:
                    discrepancies.append(
                        PurchaseOrderService._discrepancy("not_received", order_item.product, outstanding, Decimal("0"))
                    )
            return discrepancies

    @staticmethod
    def _discrepancy(kind: str, product: Product, outstanding: Decimal, received: Decimal) -> dict[str, Any]:
        """Build one discrepancy entry with what the UI needs to show it.

        Args:
            kind: "over", "under", "not_on_order" or "not_received".
            product: The product the line is for (unit loaded).
            outstanding: Quantity still outstanding on the order.
            received: Quantity on this GRN.

        Returns:
            The discrepancy dict described in ``check_receipt_discrepancies``.
        """
        if product.unit is not None:
            decimal_places = min(product.unit.decimal_places or 0, 3)
        else:
            decimal_places = 3 if product.is_weighted else 0
        return {
            "kind": kind,
            "product_id": product.id,
            "product_name": product.get_display_name(),
            "outstanding": outstanding,
            "received": received,
            "decimal_places": decimal_places,
        }
