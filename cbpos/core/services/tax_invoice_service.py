"""Tax Invoice Service — deep module for compliant Sri Lankan VAT Tax Invoices (#814).

Implements statutory requirements under:
- Value Added Tax Act No. 14 of 2002 Section 20 & Section 25
- Gazette Extraordinary No. 2481/22 and No. 2500/106
- IRD Circular SEC/2026/E/03
"""

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus
from cbpos.core.database import Database
from cbpos.core.models import (
    AuditLog,
    Sale,
    SaleItem,
)
from cbpos.core.models.tax_invoice import (
    TaxCreditNote,
    TaxInvoice,
    TaxInvoiceLine,
    TaxInvoiceSequence,
)
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.utils.amount_to_words import amount_to_words
from cbpos.core.utils.money import round_money
from cbpos.core.utils.permission_helper import check_permission_with_override

logger = logging.getLogger(__name__)

MONTH_CODES = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)

_TIN_RE = re.compile(r"^\d{9}$")


class TaxInvoiceService:
    """Service managing official VAT Tax Invoices and their statutory lifecycle."""

    @staticmethod
    def can_issue_invoices() -> tuple[bool, str | None]:
        """Check if shop configuration allows issuing VAT Tax Invoices.

        Returns:
            (can_issue, error_translation_key_or_None)
        """
        if not TaxService.is_vat_active():
            return False, "tax_invoice.error_vat_not_active"

        shop_tin = ConfigService.get("company_tax_id") or ConfigService.get("vat_number")
        if not shop_tin:
            return False, "tax_invoice.error_vat_not_active"

        terminal_mode = ConfigService.get("terminal_mode") or "standalone"
        if terminal_mode == "terminal":
            return False, "tax_invoice.network_mode_restriction"

        return True, None

    @staticmethod
    def validate_eligibility(sale_id: int, session: Session | None = None) -> tuple[bool, str | None]:
        """Validate whether a sale is legally eligible for a VAT Tax Invoice.

        Returns:
            (is_eligible, error_translation_key_or_None)
        """
        # 1. Shop must be VAT registered and have a valid TIN/VAT number configured
        can_issue, err = TaxInvoiceService.can_issue_invoices()
        if not can_issue:
            return False, err

        # 3. Sale status and window checks
        def _check_sale(s: Session) -> tuple[bool, str | None]:
            sale = s.get(Sale, sale_id)
            if not sale:
                return False, "tax_invoice.error_sale_not_found"

            if sale.status == DocumentStatus.VOID or sale.status == "VOID":
                return False, "tax_invoice.error_sale_void"

            if sale.payment_method == "REFUND" or sale.refund_of_sale_id is not None:
                return False, "tax_invoice.error_cannot_issue_on_refund"

            # 28-day statutory issue window based on sale date
            sale_date = sale.date if sale.date else datetime.now()
            if sale_date < datetime.now() - timedelta(days=28):
                return False, "tax_invoice.error_window_expired"

            return True, None

        if session is not None:
            return _check_sale(session)

        db = Database()
        with db.get_session() as s:
            return _check_sale(s)

    @staticmethod
    def get_tax_invoice_by_sale_id(sale_id: int, session: Session | None = None) -> TaxInvoice | None:
        """Lookup existing tax invoice for a sale, loading its snapshot lines."""
        if session is not None:
            return (
                session.query(TaxInvoice)
                .options(joinedload(TaxInvoice.lines))
                .filter(TaxInvoice.sale_id == sale_id)
                .first()
            )

        db = Database()
        with db.get_session() as s:
            return (
                s.query(TaxInvoice).options(joinedload(TaxInvoice.lines)).filter(TaxInvoice.sale_id == sale_id).first()
            )

    @staticmethod
    def generate_serial(
        issued_at: datetime | None = None,
        terminal_code: str | None = None,
        session: Session | None = None,
    ) -> str:
        """Generate the next atomic monotonic serial number in YYMMM_QQQQ_XXXXX format.

        Uses explicit invariant month abbreviations and atomic upsert across engines.
        """
        now = issued_at or datetime.now()
        yy = now.strftime("%y")
        mmm = MONTH_CODES[now.month - 1]

        if not terminal_code:
            tid = ConfigService.get("terminal_id") or "MAIN"
            terminal_code = re.sub(r"[^A-Za-z0-9]", "", tid).upper() or "MAIN"

        terminal_code = terminal_code[:15].upper()
        prefix = f"{yy}{mmm}_{terminal_code}"

        def _allocate_seq(s: Session) -> int:
            is_sqlite = s.bind.dialect.name == "sqlite" if s.bind else True
            if is_sqlite:
                # SQLite sequence incrementation inside transaction
                seq_row = s.query(TaxInvoiceSequence).filter_by(prefix=prefix).first()
                if not seq_row:
                    try:
                        seq_row = TaxInvoiceSequence(prefix=prefix, last_seq=1)
                        s.add(seq_row)
                        s.flush()
                        return 1
                    except IntegrityError:
                        s.rollback()
                        seq_row = s.query(TaxInvoiceSequence).filter_by(prefix=prefix).first()

                seq_row.last_seq += 1
                s.flush()
                return seq_row.last_seq
            else:
                # PostgreSQL atomic upsert + FOR UPDATE
                s.execute(
                    text(
                        "INSERT INTO tax_invoice_sequences (prefix, last_seq) "
                        "VALUES (:p, 0) ON CONFLICT (prefix) DO NOTHING"
                    ),
                    {"p": prefix},
                )
                seq_val = s.execute(
                    text("SELECT last_seq FROM tax_invoice_sequences WHERE prefix = :p FOR UPDATE"),
                    {"p": prefix},
                ).scalar_one()
                new_seq = seq_val + 1
                s.execute(
                    text("UPDATE tax_invoice_sequences SET last_seq = :s WHERE prefix = :p"),
                    {"s": new_seq, "p": prefix},
                )
                s.flush()
                return new_seq

        if session is not None:
            seq = _allocate_seq(session)
            return f"{prefix}_{seq:05d}"

        db = Database()
        with db.get_session(serializable=True) as s:
            seq = _allocate_seq(s)
            s.commit()
            return f"{prefix}_{seq:05d}"

    @staticmethod
    def validate_buyer_details(buyer_details: dict[str, Any]) -> None:
        """Validate statutory buyer particulars (Name, Address, 9-digit TIN)."""
        name = str(buyer_details.get("name", "")).strip()
        address = str(buyer_details.get("address", "")).strip()
        tin = str(buyer_details.get("tin", "")).strip()

        if not name or not address:
            raise ValueError("missing_buyer_details")

        if not _TIN_RE.match(tin):
            raise ValueError("invalid_tin")

    @staticmethod
    def issue_tax_invoice(
        sale_id: int,
        buyer_details: dict[str, Any],
        user_id: int,
        issue_language: str = "en",
    ) -> TaxInvoice:
        """Issue an official VAT Tax Invoice for a completed sale."""
        # Permission check
        user = check_permission_with_override(Permissions.SALES_TAX_INVOICE, user_id)
        if not user:
            raise PermissionError("permission_denied")

        TaxInvoiceService.validate_buyer_details(buyer_details)

        db = Database()
        with db.get_session() as session:
            # Check eligibility inside session
            ok, err_key = TaxInvoiceService.validate_eligibility(sale_id, session=session)
            if not ok:
                raise ValueError(err_key or "ineligible_sale")

            # Idempotency check: if already issued, return existing
            existing = (
                session.query(TaxInvoice).options(joinedload(TaxInvoice.lines)).filter_by(sale_id=sale_id).first()
            )
            if existing:
                return existing

            sale = (
                session.query(Sale)
                .options(
                    joinedload(Sale.items).joinedload(SaleItem.product),
                    joinedload(Sale.payments),
                )
                .filter_by(id=sale_id)
                .first()
            )
            if not sale:
                raise ValueError("sale_not_found")

            invoice = TaxInvoiceService._create_tax_invoice_in_session(
                session=session,
                sale=sale,
                buyer_details=buyer_details,
                user_id=user_id,
                issue_language=issue_language,
            )
            session.commit()

            # Record in AuditLog
            try:
                with db.get_session() as audit_session:
                    audit_log = AuditLog(
                        user_id=user_id,
                        action="TAX_INVOICE_ISSUED",
                        event_type="TRANSACTION",
                        details=f"Issued Tax Invoice {invoice.serial} for sale {sale.document_number}",
                    )
                    audit_session.add(audit_log)
                    audit_session.commit()
            except Exception as e:
                logger.warning("Could not write tax invoice audit log: %s", e)

            return invoice

    @staticmethod
    def _create_tax_invoice_in_session(
        session: Session,
        sale: Sale,
        buyer_details: dict[str, Any],
        user_id: int,
        issued_at: datetime | None = None,
        issue_language: str = "en",
    ) -> TaxInvoice:
        """Create TaxInvoice and TaxInvoiceLine records inside an open database transaction."""
        TaxInvoiceService.validate_buyer_details(buyer_details)
        now = issued_at or datetime.now()

        # Serial allocation
        serial = TaxInvoiceService.generate_serial(issued_at=now, session=session)

        # Supplier particulars snapshot
        supplier_name = str(ConfigService.get("shop_name") or "CB POS Merchant")
        supplier_address = str(ConfigService.get("shop_address") or "")
        supplier_phone = str(ConfigService.get("shop_phone") or "")
        supplier_tin = str(ConfigService.get("company_tax_id") or ConfigService.get("vat_number") or "")

        # Buyer particulars snapshot
        buyer_name = str(buyer_details["name"]).strip()
        buyer_address = str(buyer_details["address"]).strip()
        buyer_phone = str(buyer_details.get("phone", "")).strip() or None
        buyer_tin = str(buyer_details["tin"]).strip()

        # Supply date: date of the sale
        sale_date = sale.date if sale.date else now
        supply_date = sale_date.date() if isinstance(sale_date, datetime) else sale_date

        # Payment method snapshot
        payment_method = str(sale.payment_method or "CASH").upper()

        # Monetary reconciliation and line snapshots
        sale_items = sale.items or []
        subtotal_sum = sum((item.subtotal for item in sale_items), Decimal("0.00"))
        sale_discount = Decimal(str(sale.additional_discount_value or 0))
        loyalty_discount = Decimal(str(sale.loyalty_points_value or 0))
        total_bill_discount = sale_discount + loyalty_discount

        lines: list[TaxInvoiceLine] = []
        allocated_discounts = Decimal("0.00")

        # Proportional discount allocation per line
        for idx, item in enumerate(sale_items):
            if subtotal_sum > Decimal("0.00") and total_bill_discount > Decimal("0.00"):
                if idx == len(sale_items) - 1:
                    line_discount = total_bill_discount - allocated_discounts
                else:
                    line_discount = round_money(total_bill_discount * (item.subtotal / subtotal_sum))
                    allocated_discounts += line_discount
            else:
                line_discount = Decimal("0.00")

            line_net = item.subtotal - line_discount
            # VAT rate on line
            if item.vat_exempt:
                vat_rate = Decimal("0.00")
                line_vat = Decimal("0.00")
            else:
                if sale.vat_rate is not None:
                    vat_rate = Decimal(str(sale.vat_rate))
                else:
                    vat_rate = Decimal(str(ConfigService.get("tax_vat_rate") or 18.0))
                line_vat = round_money(line_net * vat_rate / Decimal("100"))

            line_total = line_net + line_vat

            product = item.product
            unit_name = "pcs"
            if product and hasattr(product, "unit") and product.unit:
                unit_name = product.unit.short_name or product.unit.name or "pcs"

            p_name = ""
            if product:
                p_name = getattr(product, "name_en", None) or getattr(product, "name", None) or ""
            if not p_name:
                p_name = f"Item {item.product_id}"

            sku = getattr(product, "sku", None) if product else None

            line = TaxInvoiceLine(
                item_number=idx + 1,
                product_id=item.product_id,
                item_code_snapshot=sku,
                product_name_snapshot=p_name,
                unit_snapshot=unit_name,
                quantity=item.qty,
                unit_price=item.unit_price,
                discount_amount=line_discount,
                net_amount=line_net,
                vat_rate=vat_rate,
                vat_amount=line_vat,
                total_amount=line_total,
            )
            lines.append(line)

        # Line total reconciliation with Sale totals
        expected_net = (
            sale.net_revenue
            if sale.net_revenue is not None
            else (sale.total_amount - (sale.tax_vat or Decimal("0.00")))
        )
        expected_vat = sale.tax_vat or Decimal("0.00")
        expected_total = sale.total_amount

        curr_net = sum((line.net_amount for line in lines), Decimal("0.00"))
        curr_vat = sum((line.vat_amount for line in lines), Decimal("0.00"))

        net_diff = expected_net - curr_net
        vat_diff = expected_vat - curr_vat

        if lines and (net_diff != Decimal("0.00") or vat_diff != Decimal("0.00")):
            # Reconcile onto the last line
            last_line = lines[-1]
            last_line.net_amount += net_diff
            last_line.vat_amount += vat_diff
            last_line.total_amount = last_line.net_amount + last_line.vat_amount

        # Consideration in words
        words = amount_to_words(expected_total, language=issue_language)

        invoice = TaxInvoice(
            sale_id=sale.id,
            serial=serial,
            issued_at=now,
            supply_date=supply_date,
            payment_method=payment_method,
            issued_by_user_id=user_id,
            supplier_name=supplier_name,
            supplier_address=supplier_address,
            supplier_phone=supplier_phone,
            supplier_tin=supplier_tin,
            buyer_name=buyer_name,
            buyer_address=buyer_address,
            buyer_phone=buyer_phone,
            buyer_tin=buyer_tin,
            issue_language=issue_language,
            print_count=0,
            original_printed_at=None,
            subtotal_amount=subtotal_sum,
            discount_amount=total_bill_discount,
            net_amount=expected_net,
            tax_vat=expected_vat,
            total_amount=expected_total,
            amount_in_words=words,
            lines=lines,
        )
        session.add(invoice)
        session.flush()
        return invoice

    @staticmethod
    def record_print(tax_invoice_id: int, user_id: int) -> TaxInvoice:
        """Record a successful print or export of a tax invoice, managing ORIGINAL/COPY ONLY state."""
        db = Database()
        with db.get_session() as session:
            inv = session.get(TaxInvoice, tax_invoice_id)
            if not inv:
                raise ValueError("tax_invoice_not_found")

            inv.print_count += 1
            if inv.print_count == 1:
                inv.original_printed_at = datetime.now()

            session.commit()
            session.refresh(inv)

            # Audit log
            try:
                with db.get_session() as audit_session:
                    audit_log = AuditLog(
                        user_id=user_id,
                        action="TAX_INVOICE_PRINT",
                        event_type="TRANSACTION",
                        details=f"Printed Tax Invoice {inv.serial} (count {inv.print_count})",
                    )
                    audit_session.add(audit_log)
                    audit_session.commit()
            except Exception as e:
                logger.warning("Could not write print audit log: %s", e)

            return inv

    @staticmethod
    def create_credit_note_in_session(
        session: Session,
        orig_sale_id: int,
        refund_sale_id: int,
        net_amount: Decimal,
        vat_amount: Decimal,
        total_amount: Decimal,
        user_id: int,
        reason: str,
    ) -> TaxCreditNote | None:
        """Create a statutory Tax Credit Note if original sale has a Tax Invoice (VAT Act s.25)."""
        orig_tax_invoice = session.query(TaxInvoice).filter(TaxInvoice.sale_id == orig_sale_id).first()
        if not orig_tax_invoice:
            return None

        # Count existing credit notes for this invoice to allocate sequence
        cn_count = (
            session.query(func.count(TaxCreditNote.id))
            .filter(TaxCreditNote.tax_invoice_id == orig_tax_invoice.id)
            .scalar()
            or 0
        )
        suffix = f"-{cn_count + 1}" if cn_count > 0 else ""
        cn_serial = f"CN{suffix}_{orig_tax_invoice.serial}"[:40]

        abs_total = abs(total_amount)
        abs_net = abs(net_amount)
        abs_vat = abs(vat_amount)
        words = amount_to_words(abs_total, language="en")

        credit_note = TaxCreditNote(
            tax_invoice_id=orig_tax_invoice.id,
            refund_sale_id=refund_sale_id,
            serial=cn_serial,
            issued_at=datetime.now(),
            issued_by_user_id=user_id,
            reason=reason or "Customer Return",
            net_amount=abs_net,
            tax_vat=abs_vat,
            total_amount=abs_total,
            amount_in_words=words,
        )
        session.add(credit_note)
        session.flush()

        try:
            audit_log = AuditLog(
                user_id=user_id,
                action="TAX_CREDIT_NOTE_ISSUED",
                event_type="TRANSACTION",
                details=f"Issued Tax Credit Note {cn_serial} for Tax Invoice {orig_tax_invoice.serial}",
            )
            session.add(audit_log)
        except Exception as e:
            logger.warning("Could not write credit note audit log: %s", e)

        return credit_note

    @staticmethod
    def get_credit_notes_by_tax_invoice_id(tax_invoice_id: int, session: Session | None = None) -> list[TaxCreditNote]:
        """Fetch all credit notes issued against a tax invoice."""
        if session is not None:
            return session.query(TaxCreditNote).filter(TaxCreditNote.tax_invoice_id == tax_invoice_id).all()
        db = Database()
        with db.get_session() as s:
            return s.query(TaxCreditNote).filter(TaxCreditNote.tax_invoice_id == tax_invoice_id).all()
