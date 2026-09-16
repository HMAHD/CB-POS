import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import joinedload

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.database import Database
from cbpos.core.models import Proforma, ProformaItem
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.document_service import DocumentService
from cbpos.core.services.tax_service import TaxService

logger = logging.getLogger(__name__)


class ProformaService:
    """Service for managing proforma invoices / quotations."""

    @staticmethod
    def create_proforma(
        items: list[dict[str, Any]],
        customer_id: int | None = None,
        validity_days: int = 30,
        notes: str | None = None,
    ) -> Proforma | None:
        """
        Create a new proforma/quotation.

        Args:
            items: List of dicts with keys: product_id, quantity, unit_price,
                   discount_type, discount_value, line_total, product_name
            customer_id: Optional customer ID.
            validity_days: Days until expiry (default 30).
            notes: Optional notes.

        Returns:
            Created Proforma or None on failure.
        """
        current_user = AuthService.get_current_user()
        if not current_user:
            logger.error("No user logged in for proforma creation")
            return None

        db = Database()
        with db.get_session() as session:
            try:
                doc_number = DocumentService.generate_number("PROFORMA")
                now = datetime.now()
                expiry = now.date() + timedelta(days=validity_days)

                # Calculate totals
                total = Decimal("0.00")
                for item in items:
                    total += Decimal(str(item["line_total"]))

                # Sri Lankan backward tax calc from MRP (via TaxService)
                taxes = TaxService.calculate_taxes(total)
                tax_vat = taxes["vat"]
                tax_sscl = taxes["sscl"]

                proforma = Proforma(
                    document_number=doc_number,
                    type="proforma",
                    date=now,
                    user_id=current_user.id,
                    status=DocumentStatus.QUOTE,
                    customer_id=customer_id,
                    total_amount=total.quantize(Decimal("0.01")),
                    tax_vat=tax_vat.quantize(Decimal("0.01")),
                    tax_sscl=tax_sscl.quantize(Decimal("0.01")),
                    validity_days=validity_days,
                    expiry_date=expiry,
                    notes=notes,
                )
                session.add(proforma)
                session.flush()

                for item_data in items:
                    proforma_item = ProformaItem(
                        proforma_id=proforma.id,
                        product_id=item_data["product_id"],
                        product_name=item_data["product_name"],
                        quantity=Decimal(str(item_data["quantity"])),
                        unit_price=Decimal(str(item_data["unit_price"])),
                        discount_type=item_data.get("discount_type", "NONE"),
                        discount_value=Decimal(str(item_data.get("discount_value", 0))),
                        line_total=Decimal(str(item_data["line_total"])),
                    )
                    session.add(proforma_item)

                session.commit()
                logger.info("Proforma %s created successfully", doc_number)
                return proforma

            except Exception as e:
                logger.error("Failed to create proforma: %s", e)
                session.rollback()
                return None

    @staticmethod
    def get_proformas(
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        customer_id: int | None = None,
        status: str | None = None,
    ) -> list[Proforma]:
        """Get proformas with optional filters."""
        db = Database()
        with db.get_session() as session:
            query = session.query(Proforma).options(
                joinedload(Proforma.customer),
                joinedload(Proforma.user),
            )

            if date_from:
                query = query.filter(Proforma.date >= date_from)
            if date_to:
                query = query.filter(Proforma.date <= date_to)
            if customer_id:
                query = query.filter(Proforma.customer_id == customer_id)
            if status:
                query = query.filter(Proforma.status == status)

            return query.order_by(Proforma.date.desc()).all()

    @staticmethod
    def get_proforma_details(proforma_id: int) -> Proforma | None:
        """Get a proforma with eager-loaded items."""
        db = Database()
        with db.get_session() as session:
            return (
                session.query(Proforma)
                .options(
                    joinedload(Proforma.items).joinedload(ProformaItem.product),
                    joinedload(Proforma.customer),
                    joinedload(Proforma.user),
                )
                .filter_by(id=proforma_id)
                .first()
            )

    @staticmethod
    def convert_to_sale(proforma_id: int) -> dict[str, Any] | None:
        """
        Prepare proforma data for conversion to a sale.

        Returns a dict with items and customer_id that can be used
        to populate the SalesView cart. Does NOT mark as converted yet -
        that happens after the sale is completed.
        """
        db = Database()
        with db.get_session() as session:
            proforma = (
                session.query(Proforma)
                .options(
                    joinedload(Proforma.items).joinedload(ProformaItem.product),
                )
                .filter_by(id=proforma_id)
                .first()
            )

            if not proforma:
                logger.error("Proforma %s not found", proforma_id)
                return None

            if proforma.status != DocumentStatus.QUOTE:
                logger.error("Proforma %s is not in QUOTE status (is %s)", proforma_id, proforma.status)
                return None

            cart_items = []
            for item in proforma.items:
                cart_items.append(
                    {
                        "product": item.product,
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                    }
                )

            return {
                "proforma_id": proforma.id,
                "customer_id": proforma.customer_id,
                "items": cart_items,
            }

    @staticmethod
    def mark_converted(proforma_id: int, sale_id: int) -> bool:
        """Mark a proforma as CONVERTED after successful sale."""
        db = Database()
        with db.get_session() as session:
            try:
                proforma = session.query(Proforma).filter_by(id=proforma_id).first()
                if proforma:
                    proforma.status = DocumentStatus.CONVERTED
                    proforma.converted_sale_id = sale_id
                    session.commit()
                    logger.info("Proforma %s marked as CONVERTED (sale %s)", proforma_id, sale_id)
                    return True
                return False
            except Exception as e:
                logger.error("Failed to mark proforma converted: %s", e)
                session.rollback()
                return False

    @staticmethod
    def void_proforma(proforma_id: int, reason_id: int | None = None) -> bool:
        """Void a proforma/quotation."""
        db = Database()
        with db.get_session() as session:
            try:
                proforma = session.query(Proforma).filter_by(id=proforma_id).first()
                if not proforma:
                    return False
                if proforma.status == DocumentStatus.VOID:
                    return False

                proforma.status = DocumentStatus.VOID
                if reason_id:
                    proforma.void_reason_id = reason_id
                session.commit()
                logger.info("Proforma %s voided", proforma_id)
                return True
            except Exception as e:
                logger.error("Failed to void proforma: %s", e)
                session.rollback()
                return False

    @staticmethod
    def expire_overdue() -> int:
        """Mark past-expiry proformas as EXPIRED. Returns count of expired."""
        db = Database()
        with db.get_session() as session:
            try:
                today = date.today()
                overdue = (
                    session.query(Proforma)
                    .filter(
                        Proforma.status == DocumentStatus.QUOTE,
                        Proforma.expiry_date < today,
                    )
                    .all()
                )

                count = 0
                for proforma in overdue:
                    proforma.status = DocumentStatus.EXPIRED
                    count += 1

                if count > 0:
                    session.commit()
                    logger.info("Expired %d overdue proformas", count)

                return count
            except Exception as e:
                logger.error("Failed to expire overdue proformas: %s", e)
                session.rollback()
                return 0
