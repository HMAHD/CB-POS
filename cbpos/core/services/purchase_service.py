from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import (
    AuditLog,
    Product,
    Purchase,
    PurchaseItem,
    PurchaseOrder,
    Role,
    Supplier,
    User,
)
from cbpos.core.services.document_service import DocumentService
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.stock_service import StockService
from cbpos.core.services.supplier_payable_service import SupplierPayableService
from cbpos.core.utils.date_ranges import range_for
from cbpos.core.utils.money import round_money, round_quantity


class _Unset:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<UNSET>"

    def __bool__(self) -> bool:
        return False


_UNSET = _Unset()


@dataclass
class GrnLine:
    """One product line received in a GRN."""

    product_id: int
    qty: Decimal
    unit_cost: Decimal
    mode: str = "AUTO"
    purchase_unit_id: Any = _UNSET
    purchase_factor: Any = _UNSET
    expected_unit_conversion_on: Any = _UNSET
    expected_base_unit_id: Any = _UNSET


@dataclass
class ValidatedGrnLine:
    """Pre-validated and normalized GRN line ready for application (#937)."""

    product: Product
    product_id: int
    base_qty: Decimal
    base_unit_cost: Decimal
    supplier_line_total: Decimal
    purchase_qty: Decimal
    purchase_unit_cost: Decimal
    purchase_factor: Decimal
    purchase_unit_id: int | None
    p_unit_name: str | None
    b_unit_name: str | None
    raw_qty: Decimal
    raw_cost: Decimal


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
    approved_by: int | None = None
    expected_unit_conversion_on: Any = _UNSET


class PurchaseService:
    """
    Service for managing purchases and stock reception (GRN).
    """

    @staticmethod
    def _validate_and_normalize_line(
        product: Product,
        raw_qty: Decimal,
        raw_cost: Decimal,
        mode: str,
        expected_base_unit_id: Any,
        purchase_unit_id: Any,
        purchase_factor: Any,
        expected_unit_conversion_on: Any,
        is_unit_conv_on: bool,
    ) -> ValidatedGrnLine:
        """Validate configuration snapshots and normalize quantities/costs (#937)."""
        if raw_qty <= Decimal("0"):
            raise ValueError(f"grn_invalid_qty: {raw_qty}")
        if raw_cost < Decimal("0.00"):
            raise ValueError(f"grn_invalid_cost: {raw_cost}")

        if expected_unit_conversion_on is not _UNSET and expected_unit_conversion_on is not None:
            if expected_unit_conversion_on != is_unit_conv_on:
                raise ValueError("stale_conversion_configuration: feature toggle changed during GRN entry")

        authoritative_factor = (
            product.purchase_factor
            if (
                isinstance(getattr(product, "purchase_factor", None), (Decimal, int, float))
                and product.purchase_factor > 0
            )
            else Decimal("1.000")
        )
        has_product_conversion = bool(isinstance(product.purchase_unit_id, int) and authoritative_factor > Decimal("0"))

        if expected_base_unit_id is not _UNSET and expected_base_unit_id != product.unit_id:
            raise ValueError(f"stale_conversion_configuration: product {product.id} base unit changed")

        if mode == "PURCHASE":
            if not is_unit_conv_on:
                raise ValueError("stale_conversion_configuration: purchase unit mode requested but feature is disabled")
            if purchase_unit_id is not _UNSET and purchase_unit_id != product.purchase_unit_id:
                raise ValueError(f"stale_conversion_configuration: product {product.id} purchase unit changed")
            if not product.purchase_unit_id:
                raise ValueError(
                    f"stale_conversion_configuration: product {product.id} has no purchase unit configured"
                )
            if (
                purchase_factor is not _UNSET
                and purchase_factor is not None
                and purchase_factor != authoritative_factor
            ):
                raise ValueError(f"stale_conversion_configuration: product {product.id} factor changed")
            use_conversion = True
        elif mode == "BASE":
            if is_unit_conv_on:
                if purchase_unit_id is not _UNSET and purchase_unit_id != product.purchase_unit_id:
                    raise ValueError(f"stale_conversion_configuration: product {product.id} purchase unit changed")
                if (
                    purchase_factor is not _UNSET
                    and purchase_factor is not None
                    and purchase_factor != authoritative_factor
                ):
                    raise ValueError(f"stale_conversion_configuration: product {product.id} factor changed")
            use_conversion = False
        else:  # AUTO
            if purchase_unit_id is not _UNSET and purchase_unit_id is not None and not is_unit_conv_on:
                raise ValueError(
                    "stale_conversion_configuration: line configured with purchase unit but feature is disabled"
                )
            if is_unit_conv_on:
                if purchase_unit_id is not _UNSET and purchase_unit_id != product.purchase_unit_id:
                    raise ValueError(f"stale_conversion_configuration: product {product.id} purchase unit changed")
                if (
                    product.purchase_unit_id is not None
                    and purchase_factor is not _UNSET
                    and purchase_factor is not None
                    and purchase_factor != authoritative_factor
                ):
                    raise ValueError(f"stale_conversion_configuration: product {product.id} factor changed")
            use_conversion = is_unit_conv_on and has_product_conversion

        if use_conversion:
            purchase_qty = raw_qty
            purchase_unit_cost = raw_cost
            purchase_factor_val = authoritative_factor
            purchase_unit_id_val = product.purchase_unit_id

            base_qty = round_quantity(purchase_qty * purchase_factor_val)
            base_unit_cost = round_money(purchase_unit_cost / purchase_factor_val)
            supplier_line_total = round_money(purchase_qty * purchase_unit_cost)
            p_unit_name = product.purchase_unit.name if product.purchase_unit else None
        else:
            purchase_qty = None
            purchase_unit_cost = None
            purchase_factor_val = Decimal("1.000")
            purchase_unit_id_val = None

            base_qty = round_quantity(raw_qty)
            base_unit_cost = round_money(raw_cost)
            supplier_line_total = round_money(raw_qty * raw_cost)
            p_unit_name = None

        if base_qty <= Decimal("0"):
            raise ValueError(f"grn_invalid_qty: {raw_qty} results in zero base quantity")

        b_unit_name = product.unit.name if product.unit else None

        return ValidatedGrnLine(
            product=product,
            product_id=product.id,
            base_qty=base_qty,
            base_unit_cost=base_unit_cost,
            supplier_line_total=supplier_line_total,
            purchase_qty=purchase_qty,
            purchase_unit_cost=purchase_unit_cost,
            purchase_factor=purchase_factor_val,
            purchase_unit_id=purchase_unit_id_val,
            p_unit_name=p_unit_name,
            b_unit_name=b_unit_name,
            raw_qty=raw_qty,
            raw_cost=raw_cost,
        )

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
            effective_user_id = request.approved_by if request.approved_by is not None else request.user_id
            if effective_user_id is not None:
                user = session.get(
                    User, effective_user_id, options=[joinedload(User.role).joinedload(Role.permissions)]
                )
                if not user or not PermissionService.user_has_permission(user, Permissions.PURCHASE_CREATE_GRN):
                    raise PermissionError(f"Permission denied: {Permissions.PURCHASE_CREATE_GRN} required")

            supplier = session.get(Supplier, request.supplier_id)
            if not supplier:
                raise ValueError(f"Supplier {request.supplier_id} not found")

            order = None
            order_items_by_product = {}
            if request.purchase_order_id:
                order = session.get(PurchaseOrder, request.purchase_order_id)
                if order:
                    order_items_by_product = {item.product_id: item for item in order.items}

            is_unit_conv_on = FeatureFlags.is_on(Features.UNIT_CONVERSION)
            if request.expected_unit_conversion_on is not _UNSET and request.expected_unit_conversion_on is not None:
                if request.expected_unit_conversion_on != is_unit_conv_on:
                    raise ValueError("stale_conversion_configuration: feature toggle changed during GRN entry")

            # Phase 1: Validate all products exist before checking configuration
            for line in request.lines:
                if not line.product_id or not session.get(Product, line.product_id):
                    raise ValueError(f"Product {line.product_id} not found")

            # Phase 2: Validate all lines and configuration before mutating state or generating numbers
            validated_lines: list[ValidatedGrnLine] = []
            for line in request.lines:
                product = session.get(Product, line.product_id)

                vline = PurchaseService._validate_and_normalize_line(
                    product=product,
                    raw_qty=line.qty,
                    raw_cost=line.unit_cost,
                    mode=getattr(line, "mode", "AUTO"),
                    expected_base_unit_id=getattr(line, "expected_base_unit_id", _UNSET),
                    purchase_unit_id=getattr(line, "purchase_unit_id", _UNSET),
                    purchase_factor=getattr(line, "purchase_factor", _UNSET),
                    expected_unit_conversion_on=getattr(line, "expected_unit_conversion_on", _UNSET),
                    is_unit_conv_on=is_unit_conv_on,
                )
                validated_lines.append(vline)

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

            for vline in validated_lines:
                order_item = order_items_by_product.get(vline.product_id)
                if order_item:
                    order_item.qty_received += vline.base_qty

                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=vline.product_id,
                    qty_received=vline.base_qty,
                    unit_cost=vline.base_unit_cost,
                    purchase_order_item_id=order_item.id if order_item else None,
                    purchase_unit_id=vline.purchase_unit_id,
                    purchase_factor=vline.purchase_factor,
                    purchase_qty=vline.purchase_qty,
                    purchase_unit_cost=vline.purchase_unit_cost,
                    purchase_unit_name=vline.p_unit_name,
                    base_unit_name=vline.b_unit_name,
                )
                session.add(purchase_item)

                total_purchase_cost += vline.supplier_line_total

                # Record stock movement and compute AVCO
                old_qty = vline.product.stock_qty
                old_cost = vline.product.cost if vline.product.cost is not None else Decimal("0.00")

                StockService.record_movement(
                    product_id=vline.product_id,
                    qty_change=vline.base_qty,
                    movement_type="PURCHASE",
                    user_id=request.user_id,
                    document_id=purchase.id,
                    session=session,
                )

                # Invariant 2: if old_qty <= 0, new_cost = base_unit_cost; else weighted average
                if old_qty <= Decimal("0"):
                    new_cost = vline.base_unit_cost
                else:
                    new_cost = round_money(
                        (old_qty * old_cost + vline.base_qty * vline.base_unit_cost) / (old_qty + vline.base_qty)
                    )
                vline.product.cost = new_cost

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
        purchase_id: int,
        items_data: list[dict[str, Any]],
        input_vat: Decimal = Decimal("0.00"),
        expected_unit_conversion_on: Any = _UNSET,
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
            expected_unit_conversion_on: Expected UNIT_CONVERSION feature state.
                Fails closed with stale_conversion_configuration if mismatched.
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
            is_unit_conv_on = FeatureFlags.is_on(Features.UNIT_CONVERSION)
            if expected_unit_conversion_on is not _UNSET and expected_unit_conversion_on is not None:
                if expected_unit_conversion_on != is_unit_conv_on:
                    raise ValueError("stale_conversion_configuration: feature toggle changed during purchase commit")

            # Phase 1: Validate all products exist before checking configuration
            for item_data in items_data:
                product_id = item_data.get("product_id")
                if not product_id or not session.get(Product, product_id):
                    raise ValueError(f"Product {product_id} not found")

            # Phase 2: Validate all items and configuration before mutating state
            validated_items: list[ValidatedGrnLine] = []
            for item_data in items_data:
                product_id = item_data.get("product_id")
                product = session.get(Product, product_id)

                raw_qty = Decimal(str(item_data.get("qty", item_data.get("quantity", "0"))))
                raw_cost = Decimal(str(item_data.get("cost", item_data.get("unit_cost", "0"))))
                mode = item_data.get("mode", "AUTO")
                if "expected_base_unit_id" in item_data:
                    expected_base_unit_id = item_data["expected_base_unit_id"]
                elif "base_unit_id" in item_data:
                    expected_base_unit_id = item_data["base_unit_id"]
                else:
                    expected_base_unit_id = _UNSET

                if "purchase_unit_id" in item_data:
                    purchase_unit_id = item_data["purchase_unit_id"]
                elif "expected_purchase_unit_id" in item_data:
                    purchase_unit_id = item_data["expected_purchase_unit_id"]
                else:
                    purchase_unit_id = _UNSET

                if "purchase_factor" in item_data and item_data["purchase_factor"] is not None:
                    purchase_factor = Decimal(str(item_data["purchase_factor"]))
                elif "expected_purchase_factor" in item_data and item_data["expected_purchase_factor"] is not None:
                    purchase_factor = Decimal(str(item_data["expected_purchase_factor"]))
                elif "purchase_factor" in item_data or "expected_purchase_factor" in item_data:
                    purchase_factor = None
                else:
                    purchase_factor = _UNSET

                if "expected_unit_conversion_on" in item_data:
                    expected_conv_on = item_data["expected_unit_conversion_on"]
                else:
                    expected_conv_on = _UNSET

                vline = PurchaseService._validate_and_normalize_line(
                    product=product,
                    raw_qty=raw_qty,
                    raw_cost=raw_cost,
                    mode=mode,
                    expected_base_unit_id=expected_base_unit_id,
                    purchase_unit_id=purchase_unit_id,
                    purchase_factor=purchase_factor,
                    expected_unit_conversion_on=expected_conv_on,
                    is_unit_conv_on=is_unit_conv_on,
                )
                validated_items.append(vline)

            for vline in validated_items:
                order_item = order_items_by_product.get(vline.product_id)
                if order_item:
                    order_item.qty_received += vline.base_qty

                # Create Purchase Item
                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=vline.product_id,
                    qty_received=vline.base_qty,
                    unit_cost=vline.base_unit_cost,
                    purchase_order_item_id=order_item.id if order_item else None,
                    purchase_unit_id=vline.purchase_unit_id,
                    purchase_factor=vline.purchase_factor,
                    purchase_qty=vline.purchase_qty,
                    purchase_unit_cost=vline.purchase_unit_cost,
                    purchase_unit_name=vline.p_unit_name,
                    base_unit_name=vline.b_unit_name,
                )
                session.add(purchase_item)

                total_purchase_cost += vline.supplier_line_total

                old_qty = vline.product.stock_qty
                old_cost = vline.product.cost if vline.product.cost is not None else Decimal("0.00")

                # 1. Update Stock & Log Movement via StockService
                StockService.record_movement(
                    product_id=vline.product_id,
                    qty_change=vline.base_qty,
                    movement_type="PURCHASE",
                    user_id=purchase.user_id,
                    document_id=purchase.id,
                    session=session,
                )

                # 2. Calculate Weighted Average Cost (Invariant 2, #899)
                if old_qty <= Decimal("0"):
                    vline.product.cost = vline.base_unit_cost
                else:
                    vline.product.cost = round_money(
                        (old_qty * old_cost + vline.base_qty * vline.base_unit_cost) / (old_qty + vline.base_qty)
                    )

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
            start_dt, end_dt = range_for(date_from, date_to)
            if start_dt:
                query = query.filter(Purchase.date >= start_dt)
            if end_dt:
                query = query.filter(Purchase.date < end_dt)

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
                    joinedload(Purchase.items).joinedload(PurchaseItem.product).joinedload(Product.unit),
                    joinedload(Purchase.items).joinedload(PurchaseItem.purchase_unit),
                    joinedload(Purchase.supplier),
                    joinedload(Purchase.user),
                )
                .filter(Purchase.id == purchase_id)
                .first()
            )
            if purchase:
                session.expunge_all()
            return purchase
