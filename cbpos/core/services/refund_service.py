"""
Refund Service — deep module for partial and full item-level refunds (#812).

Handles:
- Line-level refundable queries and quantity validations
- Proportional bill discount and loyalty redemption allocation
- Proportional VAT/SSCL calculations with remainder rule on final refunds
- Tender allocation across original payment kinds (OTHER -> CASH)
- Manager tender override to CASH or CUSTOMER_CREDIT with auditing
- Stock RETURN movements (skipping service items)
- Atomic ledger adjustments and loyalty reversals
- Derived refund states ("NONE", "PARTIAL", "FULL") for sale history lists
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import (
    DocumentStatus,
    MovementType,
    PaymentMethodKind,
    PaymentMethodType,
    Precision,
    ShiftStatus,
)
from cbpos.core.database import Database
from cbpos.core.interfaces.transaction_peripherals import RefundCompleted, TransactionPeripherals
from cbpos.core.models import (
    AuditLog,
    LoyaltyLedgerEntry,
    Role,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    User,
)
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.loyalty_service import LoyaltyService
from cbpos.core.services.payment_service import classify_method_name
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)


def round_money(val: Decimal) -> Decimal:
    """Round money value using approved ROUND_HALF_UP helper."""
    return Decimal(str(val)).quantize(Precision.MONEY, rounding=ROUND_HALF_UP)


def round_qty(val: Decimal) -> Decimal:
    """Round quantity value using approved 3-decimal precision."""
    return Decimal(str(val)).quantize(Precision.QUANTITY, rounding=ROUND_HALF_UP)


@dataclass
class RefundLineRequest:
    """Request to refund a specific quantity of a sold line item."""

    sale_item_id: int
    qty: Decimal
    reason: str | None = None

    def __post_init__(self):
        if not isinstance(self.qty, Decimal):
            self.qty = Decimal(str(self.qty))


@dataclass
class RefundableLine:
    """Available remaining line item details for refund selection."""

    sale_item_id: int
    product_id: int
    product_name: str
    sold_qty: Decimal
    refunded_qty: Decimal
    remaining_qty: Decimal
    line_refund_value_per_unit: Decimal
    subtotal: Decimal
    is_service: bool = False
    is_weighed: bool = False


@dataclass
class TenderRefundItem:
    """Amount allocated to a specific tender method upon refund."""

    payment_method: str
    kind: str
    amount: Decimal
    note: str | None = None


@dataclass
class RefundPreviewLine:
    """Preview of an individual line's calculated refund value."""

    sale_item_id: int
    product_name: str
    qty: Decimal
    refund_value: Decimal
    reason: str | None = None


@dataclass
class RefundPreview:
    """Computed preview of totals, tax breakdown, and tender allocation."""

    lines: list[RefundPreviewLine]
    total_refund_amount: Decimal
    refund_vat: Decimal
    refund_sscl: Decimal
    refund_net: Decimal
    tenders: list[TenderRefundItem]
    is_full_refund: bool


@dataclass
class RefundResult:
    """Result of an executed refund transaction."""

    refund_sale_id: int
    refund_document_number: str
    total_refund_amount: Decimal
    refund_sale: Sale
    tenders: list[TenderRefundItem]
    voucher: list[dict] | None = None


class RefundService:
    """Deep module managing the refund and return life cycle."""

    @staticmethod
    def refundable_lines(sale_id: int, session: Session | None = None) -> list[RefundableLine]:
        """Return all refundable line items for a sale."""
        if session is not None:
            return RefundService._get_refundable_lines(session, sale_id)
        db = Database()
        with db.get_session() as s:
            return RefundService._get_refundable_lines(s, sale_id)

    @staticmethod
    def _get_refundable_lines(session: Session, sale_id: int) -> list[RefundableLine]:
        sale = session.get(Sale, sale_id, options=[joinedload(Sale.items).joinedload(SaleItem.product)])
        if not sale or sale.status == DocumentStatus.VOID or sale.payment_method == "REFUND" or sale.refund_of_sale_id:
            return []

        # Check if sale has legacy full refund where items had refunded_qty == 0
        has_legacy_refund = session.query(Sale.id).filter(Sale.refund_of_sale_id == sale.id).first() is not None

        # Allocation factor for bill-level discounts
        orig_items = [it for it in sale.items if it.qty > 0]
        total_orig_subtotals = sum((it.subtotal for it in orig_items), Decimal("0.00"))
        alloc_factor = (
            (sale.total_amount / total_orig_subtotals) if total_orig_subtotals > Decimal("0.00") else Decimal("0.00")
        )

        lines: list[RefundableLine] = []
        for item in orig_items:
            product = item.product
            product_name = (
                product.get_display_name()
                if product and hasattr(product, "get_display_name")
                else (product.name_en if product else f"Item #{item.id}")
            )
            is_service = bool(product.is_service) if product else False
            is_weighed = bool(getattr(product, "is_weighted", False)) if product else False

            line_net = item.subtotal * alloc_factor
            unit_refund = (line_net / item.qty) if item.qty > Decimal("0") else Decimal("0.00")
            item_ref_qty = item.refunded_qty or Decimal("0.000")
            if has_legacy_refund and item_ref_qty == Decimal("0.000"):
                item_ref_qty = item.qty
            rem_qty = max(Decimal("0.000"), item.qty - item_ref_qty)

            lines.append(
                RefundableLine(
                    sale_item_id=item.id,
                    product_id=item.product_id,
                    product_name=product_name,
                    sold_qty=round_qty(item.qty),
                    refunded_qty=round_qty(item_ref_qty),
                    remaining_qty=round_qty(rem_qty),
                    line_refund_value_per_unit=unit_refund,
                    subtotal=item.subtotal,
                    is_service=is_service,
                    is_weighed=is_weighed,
                )
            )
        return lines

    @staticmethod
    def preview(
        sale_id: int,
        lines: list[RefundLineRequest],
        tender_override: str | None = None,
        override_reason: str | None = None,
        session: Session | None = None,
    ) -> RefundPreview:
        """Preview refund calculations (amounts, taxes, and tender allocation) without saving."""
        if session is not None:
            return RefundService._compute_preview(session, sale_id, lines, tender_override, override_reason)
        db = Database()
        with db.get_session() as s:
            return RefundService._compute_preview(s, sale_id, lines, tender_override, override_reason)

    @staticmethod
    def _compute_preview(
        session: Session,
        sale_id: int,
        lines: list[RefundLineRequest],
        tender_override: str | None = None,
        override_reason: str | None = None,
    ) -> RefundPreview:
        sale = session.get(
            Sale,
            sale_id,
            options=[
                joinedload(Sale.items).joinedload(SaleItem.product),
                joinedload(Sale.payments),
            ],
        )
        if not sale:
            raise ValueError("sale_not_found")
        if sale.status == DocumentStatus.VOID:
            raise ValueError("sale_void")
        if sale.payment_method == "REFUND" or sale.refund_of_sale_id is not None:
            raise ValueError("is_refund_document")
        if not lines:
            raise ValueError("no_lines")

        # Previous refunds of this sale
        prev_refunds = session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).all()
        prev_totals = sum((abs(r.total_amount) for r in prev_refunds), Decimal("0.00"))
        if sale.total_amount > Decimal("0.00") and prev_totals >= sale.total_amount:
            raise ValueError("qty_exceeds_remaining")

        orig_items = [it for it in sale.items if it.qty > 0]
        items_map = {it.id: it for it in orig_items}
        total_orig_subtotals = sum((it.subtotal for it in orig_items), Decimal("0.00"))
        alloc_factor = (
            (sale.total_amount / total_orig_subtotals) if total_orig_subtotals > Decimal("0.00") else Decimal("0.00")
        )

        req_qtys: dict[int, Decimal] = {}
        for req in lines:
            if req.qty <= Decimal("0"):
                raise ValueError("qty_not_positive")
            if req.sale_item_id not in items_map:
                raise ValueError(f"item_not_found: {req.sale_item_id}")
            orig = items_map[req.sale_item_id]
            current_refunded = orig.refunded_qty or Decimal("0.000")
            remaining = orig.qty - current_refunded
            if req.qty > remaining:
                raise ValueError("qty_exceeds_remaining")
            req_qtys[req.sale_item_id] = req_qtys.get(req.sale_item_id, Decimal("0.000")) + req.qty
            if req_qtys[req.sale_item_id] > remaining:
                raise ValueError("qty_exceeds_remaining")

        # Determine if this refund completes all remaining quantities on the entire sale
        is_final_refund = all(
            (req_qtys.get(it.id, Decimal("0.000")) + (it.refunded_qty or Decimal("0.000"))) >= it.qty
            for it in orig_items
        )

        # Previous refunds of this sale
        prev_refunds = session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).all()
        prev_totals = sum((abs(r.total_amount) for r in prev_refunds), Decimal("0.00"))

        # Calculate line refund values
        preview_lines: list[RefundPreviewLine] = []
        raw_values: list[Decimal] = []
        for req in lines:
            orig = items_map[req.sale_item_id]
            line_net = orig.subtotal * alloc_factor
            unit_refund = (line_net / orig.qty) if orig.qty > Decimal("0") else Decimal("0.00")
            line_val = round_money(unit_refund * req.qty)
            raw_values.append(line_val)

        # Apply remainder rule on total refund value
        if is_final_refund:
            total_value = max(Decimal("0.00"), sale.total_amount - prev_totals)
            delta = total_value - sum(raw_values, Decimal("0.00"))
            if raw_values:
                raw_values[-1] += delta
        else:
            total_value = sum(raw_values, Decimal("0.00"))

        for i, req in enumerate(lines):
            orig = items_map[req.sale_item_id]
            prod = orig.product
            prod_name = (
                prod.get_display_name()
                if prod and hasattr(prod, "get_display_name")
                else (prod.name_en if prod else f"Item #{orig.id}")
            )
            preview_lines.append(
                RefundPreviewLine(
                    sale_item_id=req.sale_item_id,
                    product_name=prod_name,
                    qty=round_qty(req.qty),
                    refund_value=raw_values[i],
                    reason=req.reason,
                )
            )

        # Taxes: proportional or remainder rule
        if sale.total_amount > Decimal("0.00") and total_value > Decimal("0.00"):
            if is_final_refund:
                prev_vat = sum((abs(r.tax_vat or Decimal("0.00")) for r in prev_refunds), Decimal("0.00"))
                prev_sscl = sum((abs(r.tax_sscl or Decimal("0.00")) for r in prev_refunds), Decimal("0.00"))
                refund_vat = (sale.tax_vat or Decimal("0.00")) - prev_vat
                refund_sscl = (sale.tax_sscl or Decimal("0.00")) - prev_sscl
                refund_net = total_value - refund_vat - refund_sscl
            else:
                refund_vat = round_money((sale.tax_vat or Decimal("0.00")) * total_value / sale.total_amount)
                refund_sscl = round_money((sale.tax_sscl or Decimal("0.00")) * total_value / sale.total_amount)
                refund_net = total_value - refund_vat - refund_sscl
        else:
            refund_vat = Decimal("0.00")
            refund_sscl = Decimal("0.00")
            refund_net = Decimal("0.00")

        # Tender allocation
        tenders = RefundService._allocate_tenders(sale, total_value, tender_override, override_reason)

        return RefundPreview(
            lines=preview_lines,
            total_refund_amount=total_value,
            refund_vat=refund_vat,
            refund_sscl=refund_sscl,
            refund_net=refund_net,
            tenders=tenders,
            is_full_refund=is_final_refund,
        )

    @staticmethod
    def _allocate_tenders(
        sale: Sale,
        total_value: Decimal,
        tender_override: str | None = None,
        override_reason: str | None = None,
    ) -> list[TenderRefundItem]:
        """Allocate refund amount to tenders (proportional or override)."""
        if total_value <= Decimal("0.00"):
            return []

        if tender_override:
            override_kind = tender_override.strip().upper()
            if override_kind in ("CREDIT", "CUSTOMER_CREDIT"):
                if not sale.customer_id:
                    raise ValueError("credit_override_needs_customer")
                if not override_reason or not str(override_reason).strip():
                    raise ValueError("override_needs_reason")
                return [
                    TenderRefundItem(
                        payment_method="Credit",
                        kind=PaymentMethodKind.CREDIT,
                        amount=total_value,
                        note="Customer credit reduced",
                    )
                ]
            elif override_kind == "CASH":
                if not override_reason or not str(override_reason).strip():
                    raise ValueError("override_needs_reason")
                return [
                    TenderRefundItem(
                        payment_method="Cash",
                        kind=PaymentMethodKind.CASH,
                        amount=total_value,
                        note="Cash handed back from drawer",
                    )
                ]
            else:
                raise ValueError(f"invalid_tender_override: {tender_override}")

        # Proportional tender allocation
        payments = sale.payments
        if not payments:
            kind = classify_method_name(sale.payment_method)
            orig_tenders = [(sale.payment_method, kind, sale.total_amount)]
        else:
            orig_tenders = [(p.payment_method, p.method_kind, p.amount) for p in payments]

        mapped_tenders: list[tuple[str, str, Decimal]] = []
        for method_name, kind, amt in orig_tenders:
            if kind == PaymentMethodKind.OTHER or kind == "OTHER":
                mapped_tenders.append((PaymentMethodType.CASH, PaymentMethodKind.CASH, amt))
            else:
                mapped_tenders.append((method_name, kind, amt))

        kind_totals: dict[str, Decimal] = {}
        kind_names: dict[str, str] = {}
        for method_name, kind, amt in mapped_tenders:
            kind_totals[kind] = kind_totals.get(kind, Decimal("0.00")) + amt
            if kind not in kind_names:
                kind_names[kind] = method_name

        tenders: list[TenderRefundItem] = []
        if sale.total_amount > Decimal("0.00"):
            kinds_list = list(kind_totals.keys())
            allocated_sum = Decimal("0.00")
            for i, k in enumerate(kinds_list):
                if i == len(kinds_list) - 1:
                    share_amt = total_value - allocated_sum
                else:
                    share = kind_totals[k] / sale.total_amount
                    share_amt = round_money(total_value * share)
                    allocated_sum += share_amt
                if share_amt > Decimal("0.00"):
                    note = None
                    if k == PaymentMethodKind.CASH:
                        note = "Cash handed back from drawer"
                    elif k in (PaymentMethodKind.CARD, "CARD"):
                        note = f"Reverse {format_currency(share_amt)} on card machine"
                    elif k in (PaymentMethodKind.QR, "QR"):
                        note = f"Reverse {format_currency(share_amt)} on QR terminal"
                    elif k in (PaymentMethodKind.CREDIT, "CREDIT"):
                        note = "Customer credit reduced"
                    tenders.append(
                        TenderRefundItem(
                            payment_method=kind_names[k],
                            kind=k,
                            amount=share_amt,
                            note=note,
                        )
                    )
        return tenders

    @staticmethod
    def refund(
        sale_id: int,
        lines: list[RefundLineRequest],
        reason: str,
        user_id: int,
        *,
        tender_override: str | None = None,
        override_reason: str | None = None,
        peripherals: TransactionPeripherals | None = None,
    ) -> RefundResult:
        """Execute a refund transaction atomically."""
        db = Database()
        with db.get_session() as session:
            # 1. Permission checks
            all_system_perms = set(Permissions.get_all())
            user = session.get(User, user_id, options=[joinedload(User.role).joinedload(Role.permissions)])
            if user and user.role and user.role.name != "Admin":
                user_perm_codes = {p.code for p in (user.role.permissions or [])}
                if any(code in all_system_perms for code in user_perm_codes):
                    if Permissions.SALES_REFUND not in user_perm_codes:
                        raise ValueError("permission_denied")
                    if tender_override and Permissions.SALES_REFUND_OVERRIDE_TENDER not in user_perm_codes:
                        raise ValueError("permission_denied")

            # 2. Lock original sale (with_for_update)
            sale = session.get(
                Sale,
                sale_id,
                with_for_update=True,
                options=[
                    joinedload(Sale.items).joinedload(SaleItem.product),
                    joinedload(Sale.payments),
                ],
            )
            if not sale:
                raise ValueError("sale_not_found")
            if sale.status == DocumentStatus.VOID:
                raise ValueError("sale_void")
            if sale.payment_method == "REFUND" or sale.refund_of_sale_id is not None:
                raise ValueError("is_refund_document")

            # 3. Calculate preview allocations
            preview = RefundService._compute_preview(
                session, sale_id, lines, tender_override=tender_override, override_reason=override_reason
            )

            # 4. Open shift identification
            terminal_id = ConfigService.get("terminal_id") or "TERM-01"
            open_shift = session.scalars(
                select(Shift.id).where(
                    Shift.user_id == user_id,
                    Shift.terminal_id == terminal_id,
                    Shift.status == ShiftStatus.OPEN,
                )
            ).first()

            # 5. Create refund Sale
            refund_sale = Sale(
                date=datetime.now(),
                total_amount=-preview.total_refund_amount,
                tax_vat=-preview.refund_vat,
                tax_sscl=-preview.refund_sscl,
                net_revenue=-preview.refund_net,
                payment_method="REFUND",
                status=DocumentStatus.COMPLETED,
                user_id=user_id,
                customer_id=sale.customer_id,
                refund_of_sale_id=sale.id,
                refund_tender_override=tender_override.upper() if tender_override else None,
                terminal_id=terminal_id,
                origin_terminal_id=terminal_id,
                shift_id=open_shift,
            )
            TransactionService._insert_numbered(session, refund_sale, "RETURN")
            refund_receipt_no = refund_sale.document_number

            # 6. Create refund SaleItem rows, update original refunded_qty, and reverse stock
            orig_items_map = {it.id: it for it in sale.items if it.qty > 0}
            product_ids = [orig_items_map[req.sale_item_id].product_id for req in lines]
            composite_map = TransactionService._fetch_composite_map(session, product_ids)

            for i, req in enumerate(lines):
                orig_item = orig_items_map[req.sale_item_id]
                line_val = preview.lines[i].refund_value
                refund_item = SaleItem(
                    sale_id=refund_sale.id,
                    product_id=orig_item.product_id,
                    qty=-req.qty,
                    unit_price=orig_item.unit_price,
                    original_price=orig_item.original_price or orig_item.unit_price,
                    subtotal=-line_val,
                    refund_of_item_id=orig_item.id,
                    refund_reason=req.reason or reason,
                )
                session.add(refund_item)
                orig_item.refunded_qty = (orig_item.refunded_qty or Decimal("0.000")) + req.qty

                # Reverse stock via StockService
                TransactionService._move_stock(
                    session,
                    composite_map,
                    orig_item.product_id,
                    req.qty,
                    MovementType.RETURN,
                    refund_sale.id,
                    user_id,
                )

            # 7. Customer credit reversal if CREDIT tender allocated
            credit_tender = next((t for t in preview.tenders if t.kind == PaymentMethodKind.CREDIT), None)
            credit_reversed = Decimal("0.00")
            if credit_tender and credit_tender.amount > Decimal("0.00") and sale.customer_id:
                credit_entry = CustomerCreditService.reverse_credit_sale_in_session(
                    session,
                    sale,
                    "REFUND",
                    user_id,
                    reference_doc=refund_receipt_no,
                    amount=credit_tender.amount,
                )
                if credit_entry:
                    credit_reversed = -credit_entry.amount

            # 8. Loyalty adjustments
            if sale.customer_id:
                earned_ledger = (
                    session.query(func.coalesce(func.sum(LoyaltyLedgerEntry.points), 0))
                    .filter(
                        LoyaltyLedgerEntry.customer_id == sale.customer_id,
                        LoyaltyLedgerEntry.reference_id == sale.id,
                        LoyaltyLedgerEntry.entry_type == "EARN",
                    )
                    .scalar()
                )
                earned_pts = int(earned_ledger) if earned_ledger else int(sale.loyalty_points_earned or 0)
                already_rev_pts = -(
                    session.query(func.coalesce(func.sum(LoyaltyLedgerEntry.points), 0))
                    .filter(
                        LoyaltyLedgerEntry.customer_id == sale.customer_id,
                        LoyaltyLedgerEntry.reference_id == sale.id,
                        LoyaltyLedgerEntry.entry_type == "REVERSAL",
                        LoyaltyLedgerEntry.points < 0,
                    )
                    .scalar()
                )

                if preview.is_full_refund:
                    pts_to_reverse = max(0, int(earned_pts) - int(already_rev_pts))
                elif sale.total_amount > Decimal("0.00"):
                    pts_to_reverse = math.floor(Decimal(earned_pts) * preview.total_refund_amount / sale.total_amount)
                else:
                    pts_to_reverse = 0

                if pts_to_reverse > 0:
                    LoyaltyService.reverse_sale_points(session, sale, reason="REFUND", points=pts_to_reverse)

                if sale.loyalty_points_redeemed:
                    redeemed_pts = int(sale.loyalty_points_redeemed)
                    already_ret_pts = (
                        session.query(func.coalesce(func.sum(LoyaltyLedgerEntry.points), 0))
                        .filter(
                            LoyaltyLedgerEntry.customer_id == sale.customer_id,
                            LoyaltyLedgerEntry.reference_id == sale.id,
                            LoyaltyLedgerEntry.entry_type == "REVERSAL",
                            LoyaltyLedgerEntry.points > 0,
                        )
                        .scalar()
                    )
                    if preview.is_full_refund:
                        pts_to_return = max(0, redeemed_pts - int(already_ret_pts))
                    elif sale.total_amount > Decimal("0.00"):
                        pts_to_return = math.floor(
                            Decimal(redeemed_pts) * preview.total_refund_amount / sale.total_amount
                        )
                    else:
                        pts_to_return = 0

                    if pts_to_return > 0:
                        LoyaltyService.return_redeemed_points(session, sale, reason="REFUND", points=pts_to_return)

            # 9. SalePayment rows on refund sale
            if preview.tenders:
                for t in preview.tenders:
                    sp = SalePayment(
                        sale_id=refund_sale.id,
                        payment_method=t.payment_method,
                        method_kind=t.kind,
                        amount=-t.amount,
                    )
                    session.add(sp)
            else:
                sp = SalePayment(
                    sale_id=refund_sale.id,
                    payment_method="REFUND",
                    method_kind=PaymentMethodKind.REFUND_LEGACY,
                    amount=-preview.total_refund_amount,
                )
                session.add(sp)

            # 10. Audit log entries
            session.add(
                AuditLog(
                    user_id=user_id,
                    action="REFUND",
                    event_type="TRANSACTION",
                    details=(
                        f"Refunded sale {sale.document_number} as {refund_receipt_no}. "
                        f"Total: {preview.total_refund_amount}. Reason: {reason}"
                    ),
                )
            )
            if tender_override:
                session.add(
                    AuditLog(
                        user_id=user_id,
                        action="REFUND_TENDER_OVERRIDE",
                        event_type="TRANSACTION",
                        details=(
                            f"Refund {refund_receipt_no} tender overridden to {tender_override}. "
                            f"Reason: {override_reason}"
                        ),
                    )
                )

            # 11. Build voucher receipt before commit while relations loaded
            voucher = TransactionService._build_refund_receipt(session, sale, refund_sale, credit_reversed)
            completed = RefundCompleted(refund_sale, voucher)
            refund_id = refund_sale.id

        # 12. Hardware notification after successful commit
        try:
            (peripherals or TransactionService._peripherals).refund_completed(completed)
        except Exception as e:
            logger.error("Refund voucher for %s failed: %s", refund_receipt_no, e)

        return RefundResult(
            refund_sale_id=refund_id,
            refund_document_number=refund_receipt_no,
            total_refund_amount=preview.total_refund_amount,
            refund_sale=refund_sale,
            tenders=preview.tenders,
            voucher=voucher,
        )

    @staticmethod
    def refund_state(sale_id: int, session: Session | None = None) -> Literal["NONE", "PARTIAL", "FULL"]:
        """Return the refund state for a single sale ("NONE", "PARTIAL", or "FULL")."""
        states = RefundService.refund_states([sale_id], session=session)
        return states.get(sale_id, "NONE")  # type: ignore

    @staticmethod
    def refund_states(sale_ids: list[int], session: Session | None = None) -> dict[int, str]:
        """Return derived refund states for multiple sales in a single batched SQL query."""
        if not sale_ids:
            return {}

        if session is not None:
            return RefundService._fetch_refund_states(session, sale_ids)
        db = Database()
        with db.get_session() as s:
            return RefundService._fetch_refund_states(s, sale_ids)

    @staticmethod
    def _fetch_refund_states(session: Session, sale_ids: list[int]) -> dict[int, str]:
        # Subquery 1: summarize SaleItem quantities
        item_summary = (
            select(
                SaleItem.sale_id.label("sale_id"),
                func.count(SaleItem.id).label("item_count"),
                func.sum(case((SaleItem.refunded_qty >= SaleItem.qty, 1), else_=0)).label("fully_refunded_count"),
                func.sum(SaleItem.refunded_qty).label("total_refunded_qty"),
            )
            .where(SaleItem.sale_id.in_(sale_ids), SaleItem.qty > 0)
            .group_by(SaleItem.sale_id)
            .subquery()
        )

        # Subquery 2: count refund documents referencing this sale
        refund_docs = (
            select(
                Sale.refund_of_sale_id.label("refund_of_sale_id"),
                func.count(Sale.id).label("refund_count"),
            )
            .where(Sale.refund_of_sale_id.in_(sale_ids))
            .group_by(Sale.refund_of_sale_id)
            .subquery()
        )

        stmt = (
            select(
                Sale.id,
                func.coalesce(item_summary.c.item_count, 0).label("item_count"),
                func.coalesce(item_summary.c.fully_refunded_count, 0).label("fully_refunded_count"),
                func.coalesce(item_summary.c.total_refunded_qty, 0).label("total_refunded_qty"),
                func.coalesce(refund_docs.c.refund_count, 0).label("refund_count"),
            )
            .select_from(Sale)
            .outerjoin(item_summary, item_summary.c.sale_id == Sale.id)
            .outerjoin(refund_docs, refund_docs.c.refund_of_sale_id == Sale.id)
            .where(Sale.id.in_(sale_ids))
        )

        rows = session.execute(stmt).all()
        results: dict[int, str] = dict.fromkeys(sale_ids, "NONE")

        for row in rows:
            if row.item_count > 0:
                if row.fully_refunded_count == row.item_count:
                    results[row.id] = "FULL"
                elif row.total_refunded_qty > Decimal("0.000"):
                    results[row.id] = "PARTIAL"
                elif row.refund_count > 0:
                    results[row.id] = "FULL"
                else:
                    results[row.id] = "NONE"
            else:
                if row.refund_count > 0:
                    results[row.id] = "FULL"
                else:
                    results[row.id] = "NONE"

        return results
