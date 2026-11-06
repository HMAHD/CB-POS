from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from cbpos.core.constants.status import Precision
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Product, Purchase, PurchaseItem, PurchaseOrder, StockMovement, Supplier
from cbpos.core.services.document_service import DocumentService
from cbpos.core.services.stock_service import StockService
from cbpos.core.services.supplier_payable_service import SupplierPayableService
from cbpos.core.utils.money import round_money


@dataclass
class GrnLine:
    """One product line received in a GRN."""

    product_id: int
    qty: Decimal
    unit_cost: Decimal


@dataclass
class GrnRequest:
    """Payload for committing a GRN in a single atomic transaction."""

    supplier_id: int
    date_received: datetime
    supplier_invoice_no: str
    input_vat: Decimal
    lines: list[GrnLine]
    user_id: int
    purchase_order_id: int | None = None


class PurchaseService:
    """
    Service for managing purchases and stock reception (GRN).
    """

    @staticmethod
    def receive_goods(request: GrnRequest) -> Purchase:
        """Receive goods (GRN) in a single atomic transaction.

        Validates all inputs, allocates the document number inside the session,
        inserts header and lines, records stock movements and AVCO, updates
        supplier payable and ledger, and writes an audit log row.

        On any error, rolls back everything so no partial state or orphan
        document remains.
        """
        if not request.lines:
            raise ValueError("grn_no_items")
        if request.input_vat < Decimal("0.00"):
            raise ValueError("grn_invalid_vat")
        if request.date_received.date() > datetime.now().date():
            raise ValueError("grn_future_date")

        for line in request.lines:
            if line.qty <= Decimal("0"):
                raise ValueError(f"grn_invalid_qty: {line.qty}")
            if line.unit_cost < Decimal("0.00"):
                raise ValueError(f"grn_invalid_cost: {line.unit_cost}")

        db = Database()
        with db.get_session() as session:
            supplier = session.get(Supplier, request.supplier_id)
            if not supplier:
                raise ValueError(f"Supplier {request.supplier_id} not found")

            order = None
            order_items_by_product = {}
            if request.purchase_order_id:
                order = session.get(PurchaseOrder, request.purchase_order_id)
                if order:
                    order_items_by_product = {item.product_id: item for item in order.items}

            # Generate number inside caller session so rollback avoids gap in numbering
            doc_number = DocumentService.generate_number("PURCHASE", session=session)

            purchase = Purchase(
                document_number=doc_number,
                type="purchase",
                date=request.date_received,
                user_id=request.user_id,
                status="COMPLETED",
                reference_external=request.supplier_invoice_no,
                supplier_id=request.supplier_id,
                total_cost=Decimal("0.00"),
                input_vat=request.input_vat,
                purchase_order_id=request.purchase_order_id,
            )
            session.add(purchase)
            session.flush()

            total_purchase_cost = Decimal("0.00")

            for line in request.lines:
                product = session.get(Product, line.product_id)
                if not product:
                    raise ValueError(f"Product {line.product_id} not found")

                order_item = order_items_by_product.get(line.product_id)
                if order_item:
                    order_item.qty_received += line.qty

                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=line.product_id,
                    qty_received=line.qty,
                    unit_cost=line.unit_cost,
                    purchase_order_item_id=order_item.id if order_item else None,
                )
                session.add(purchase_item)

                total_purchase_cost += line.qty * line.unit_cost

                # Record stock movement and compute AVCO
                old_qty = product.stock_qty
                old_cost = product.cost if product.cost is not None else Decimal("0.00")

                StockService.record_movement(
                    product_id=line.product_id,
                    qty_change=line.qty,
                    movement_type="PURCHASE",
                    user_id=request.user_id,
                    document_id=purchase.id,
                    session=session,
                )

                # Invariant 2: if old_qty <= 0, new_cost = unit_cost; else weighted average
                if old_qty <= Decimal("0"):
                    new_cost = line.unit_cost
                else:
                    new_cost = round_money((old_qty * old_cost + line.qty * line.unit_cost) / (old_qty + line.qty))
                product.cost = new_cost

            purchase.total_cost = total_purchase_cost

            if order:
                order.status = (
                    "RECEIVED"
                    if all(item.qty_received >= item.qty_ordered for item in order.items)
                    else "PARTIALLY_RECEIVED"
                )

            # Update supplier payable and ledger
            supplier.current_payable += total_purchase_cost
            SupplierPayableService.record_purchase_in_session(
                session,
                supplier.id,
                purchase.id,
                total_purchase_cost,
                purchase.document_number,
                supplier.current_payable,
                purchase.user_id,
            )

            # Audit log
            log = AuditLog(
                user_id=purchase.user_id,
                action="COMMIT_PURCHASE",
                event_type="PURCHASE",
                details=(
                    f"Committed GRN {purchase.document_number} "
                    f"({len(request.lines)} item(s), total cost {total_purchase_cost:.2f})."
                ),
            )
            session.add(log)

            session.commit()
            session.refresh(purchase)
            return purchase

    @staticmethod
    def create_purchase(
        supplier_id: int,
        reference_external: str,  # Vendor Invoice #
        user_id: int,
        date_received: datetime | None = None,
        purchase_order_id: int | None = None,
    ) -> Purchase:
        """
        Create a new purchase (GRN) header in DRAFT status.

        Args:
            purchase_order_id: the Purchase Order this GRN is receiving
                against, if any (#486). A single order may be received via
                multiple separate GRNs over time.
        """
        if date_received is None:
            date_received = datetime.now()

        # Generate internal GRN number
        document_number = DocumentService.generate_number("PURCHASE")

        db = Database()
        with db.get_session() as session:
            purchase = Purchase(
                document_number=document_number,
                type="purchase",  # Polymorphic identity
                date=date_received,
                user_id=user_id,
                status="DRAFT",
                reference_external=reference_external,
                supplier_id=supplier_id,
                total_cost=Decimal("0.00"),
                purchase_order_id=purchase_order_id,
            )
            session.add(purchase)
            session.commit()
            session.refresh(purchase)
            return purchase

    @staticmethod
    def commit_purchase(
        purchase_id: int, items_data: list[dict[str, Any]], input_vat: Decimal = Decimal("0.00")
    ) -> Purchase:
        """
        Commit a purchase:
        1. Create PurchaseItems.
        2. Update stock quantity.
        3. Update product cost price (Weighted Average).
        4. Log StockMovement.
        5. Mark purchase as COMPLETED.

        items_data format: [{'product_id': int, 'qty': Decimal, 'cost': Decimal}]

        Args:
            input_vat: VAT amount shown on the supplier's invoice for this
                GRN, entered manually (not computed). Deductible against
                Output VAT in TaxLiabilityReport.
        """
        db = Database()
        with db.get_session() as session:
            purchase = session.get(Purchase, purchase_id)
            if not purchase:
                raise ValueError("Purchase not found")
            if purchase.status == "COMPLETED":
                raise ValueError("Purchase already committed")

            order = None
            order_items_by_product = {}
            if purchase.purchase_order_id:
                order = session.get(PurchaseOrder, purchase.purchase_order_id)
                if order:
                    order_items_by_product = {item.product_id: item for item in order.items}

            total_purchase_cost = Decimal("0.00")

            for item_data in items_data:
                product_id = item_data["product_id"]
                qty_received = Decimal(str(item_data["qty"]))
                unit_cost = Decimal(str(item_data["cost"]))

                order_item = order_items_by_product.get(product_id)
                if order_item:
                    order_item.qty_received += qty_received

                # Create Purchase Item
                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=product_id,
                    qty_received=qty_received,
                    unit_cost=unit_cost,
                    purchase_order_item_id=order_item.id if order_item else None,
                )
                session.add(purchase_item)

                total_purchase_cost += qty_received * unit_cost

                # Update Product Stock & Cost
                product = session.get(Product, product_id)
                if not product:
                    continue

                old_qty = product.stock_qty
                old_cost = product.cost

                # 1. Update Stock
                product.stock_qty += qty_received

                # 2. Calculate Weighted Average Cost
                # Formula: ((OldQty * OldCost) + (NewQty * NewCost)) / (OldQty + NewQty)
                total_old_value = old_qty * old_cost
                total_new_value = qty_received * unit_cost
                total_qty = old_qty + qty_received

                if total_qty > 0:
                    new_avg_cost = (total_old_value + total_new_value) / total_qty
                    product.cost = new_avg_cost.quantize(Precision.MONEY)

                # 3. Log Stock Movement
                movement = StockMovement(
                    product_id=product.id,
                    user_id=purchase.user_id,
                    timestamp=datetime.now(),
                    qty_change=qty_received,
                    balance_after=product.stock_qty,
                    document_id=purchase.id,
                    type="PURCHASE",
                )
                session.add(movement)

            # Finalize Purchase
            purchase.total_cost = total_purchase_cost
            purchase.input_vat = input_vat
            purchase.status = "COMPLETED"

            if order:
                order.status = (
                    "RECEIVED"
                    if all(item.qty_received >= item.qty_ordered for item in order.items)
                    else "PARTIALLY_RECEIVED"
                )

            # Update supplier payable
            supplier = session.get(Supplier, purchase.supplier_id)
            if supplier:
                supplier.current_payable += total_purchase_cost
                SupplierPayableService.record_purchase_in_session(
                    session,
                    supplier.id,
                    purchase.id,
                    total_purchase_cost,
                    purchase.document_number,
                    supplier.current_payable,
                    purchase.user_id,
                )

            log = AuditLog(
                user_id=purchase.user_id,
                action="COMMIT_PURCHASE",
                event_type="PURCHASE",
                details=(
                    f"Committed GRN {purchase.document_number} "
                    f"({len(items_data)} item(s), total cost {total_purchase_cost:.2f})."
                ),
            )
            session.add(log)

            session.commit()
            session.refresh(purchase)
            return purchase

    @staticmethod
    def get_all_purchases(
        status: str | None = None,
        supplier_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 500,
    ) -> list[Purchase]:
        """
        Get filtered list of purchases with eager-loaded relationships.

        Args:
            status: Filter by document status (COMPLETED, DRAFT, VOID).
            supplier_id: Filter by supplier.
            date_from: Filter from date.
            date_to: Filter to date.
            limit: Max results.

        Returns:
            List of Purchase objects ordered by date descending.
        """
        db = Database()
        with db.get_session() as session:
            query = session.query(Purchase).options(
                joinedload(Purchase.supplier),
                joinedload(Purchase.items),
                joinedload(Purchase.user),
            )

            if status:
                query = query.filter(Purchase.status == status)
            if supplier_id:
                query = query.filter(Purchase.supplier_id == supplier_id)
            if date_from:
                query = query.filter(Purchase.date >= date_from)
            if date_to:
                query = query.filter(Purchase.date <= date_to)

            purchases = query.order_by(Purchase.date.desc()).limit(limit).all()
            for p in purchases:
                session.expunge(p)
            return purchases

    @staticmethod
    def get_purchase_count() -> int:
        """Get total count of purchases."""
        db = Database()
        with db.get_session() as session:
            return session.query(func.count(Purchase.id)).scalar() or 0

    @staticmethod
    def get_purchase(purchase_id: int) -> Purchase | None:
        """Fetch a single purchase by id with items (and their products), supplier, and user eager-loaded."""
        db = Database()
        with db.get_session() as session:
            purchase = (
                session.query(Purchase)
                .options(
                    joinedload(Purchase.items).joinedload(PurchaseItem.product),
                    joinedload(Purchase.supplier),
                    joinedload(Purchase.user),
                )
                .get(purchase_id)
            )
            if purchase:
                session.expunge(purchase)
            return purchase
