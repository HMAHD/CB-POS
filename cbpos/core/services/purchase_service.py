from datetime import datetime
from decimal import Decimal
from typing import List, Tuple, Optional
from cbpos.core.models import Purchase, PurchaseItem, Product, InventoryLog
from cbpos.core.database import get_db_session


class PurchaseService:
    """
    Service for managing purchases and stock reception (GRN).
    """

    @staticmethod
    def create_purchase(
        supplier_id: int,
        reference_no: str,
        items: List[Tuple[int, Decimal, Decimal]],  # (product_id, qty, unit_cost)
        date_received: Optional[datetime] = None,
    ) -> Purchase:
        """
        Create a new purchase (GRN) in DRAFT status.
        """
        if date_received is None:
            date_received = datetime.now()

        total_cost = sum(qty * cost for _, qty, cost in items)

        with get_db_session() as session:
            purchase = Purchase(
                supplier_id=supplier_id,
                reference_no=reference_no,
                date_received=date_received,
                total_cost=total_cost,
                status="DRAFT",
            )
            session.add(purchase)
            session.flush()  # Get ID

            for prod_id, qty, cost in items:
                item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=prod_id,
                    qty_received=qty,
                    unit_cost=cost,
                )
                session.add(item)

            session.commit()
            session.refresh(purchase)
            return purchase

    @staticmethod
    def commit_purchase(purchase_id: int, user_id: int) -> Purchase:
        """
        Commit a purchase:
        1. Update stock quantity.
        2. Update product cost price (Weighted Average).
        3. Log inventory change.
        4. Mark purchase as COMPLETED.
        """
        with get_db_session() as session:
            purchase = session.get(Purchase, purchase_id)
            if not purchase:
                raise ValueError("Purchase not found")
            if purchase.status == "COMPLETED":
                raise ValueError("Purchase already committed")

            for item in purchase.items:
                product = session.get(Product, item.product_id)
                if not product:
                    continue

                old_qty = product.stock_qty
                old_cost = product.cost
                new_qty_received = item.qty_received
                new_unit_cost = item.unit_cost

                # 1. Update Stock
                product.stock_qty += new_qty_received

                # 2. Calculate Weighted Average Cost
                # Formula: ((OldQty * OldCost) + (NewQty * NewCost)) / (OldQty + NewQty)
                total_old_value = old_qty * old_cost
                total_new_value = new_qty_received * new_unit_cost
                total_qty = old_qty + new_qty_received

                if total_qty > 0:
                    new_avg_cost = (total_old_value + total_new_value) / total_qty
                    product.cost = new_avg_cost

                # 3. Log Inventory Change
                log = InventoryLog(
                    product_id=product.id,
                    qty_change=new_qty_received,
                    new_qty=product.stock_qty,
                    reason=f"GRN: {purchase.reference_no}",
                    user_id=user_id,
                    timestamp=datetime.now(),
                )
                session.add(log)

            purchase.status = "COMPLETED"
            session.commit()
            session.refresh(purchase)
            return purchase

    @staticmethod
    def get_purchase(purchase_id: int) -> Optional[Purchase]:
        with get_db_session() as session:
            return session.get(Purchase, purchase_id)
