from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import PurchaseOrder, PurchaseOrderItem
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
        """Compare GRN line quantities against each order line's outstanding
        qty (qty_ordered - qty_received so far). Returns one entry per line
        whose received qty this GRN doesn't match what's outstanding --
        over-receipt or under-receipt alike -- for the caller to confirm
        with the cashier before committing.

        items_data format: [{'product_id': int, 'qty': Decimal, ...}]
        """
        order = PurchaseOrderService.get_order(order_id)
        if not order:
            return []

        order_items_by_product = {item.product_id: item for item in order.items}

        discrepancies = []
        for data in items_data:
            order_item = order_items_by_product.get(data["product_id"])
            if not order_item:
                continue
            outstanding = order_item.qty_ordered - order_item.qty_received
            received = Decimal(str(data["qty"]))
            if received != outstanding:
                discrepancies.append(
                    {
                        "product_name": order_item.product.name_en,
                        "outstanding": outstanding,
                        "received": received,
                    }
                )
        return discrepancies
