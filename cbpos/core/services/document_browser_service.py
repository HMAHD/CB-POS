import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import (
    Document,
    Proforma,
    ProformaItem,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
)
from cbpos.core.utils.formatters import escape_like

logger = logging.getLogger(__name__)


class DocumentBrowserService:
    """Service for unified cross-type document search and detail retrieval."""

    @staticmethod
    def search_documents(
        doc_type: str | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search_term: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """
        Search documents across all types with filtering and pagination.

        Returns:
            Dict with keys: documents (list of dicts), total (int), page (int)
        """
        db = Database()
        with db.get_session() as session:
            # Base query on Document with polymorphic + relationship loading
            query = session.query(Document).options(
                joinedload(Document.user),
                joinedload(Sale.customer),
                joinedload(Purchase.supplier),
                joinedload(Proforma.customer),
            )

            # Type filter — map friendly names to polymorphic identities
            type_map = {
                "SALE": "sale",
                "PURCHASE": "purchase",
                "PROFORMA": "proforma",
            }
            if doc_type and doc_type in type_map:
                query = query.filter(Document.type == type_map[doc_type])

            # Status filter
            if status:
                query = query.filter(Document.status == status)

            # Date range
            if date_from:
                query = query.filter(Document.date >= date_from)
            if date_to:
                query = query.filter(Document.date <= date_to)

            # Search term — search document_number
            if search_term:
                escaped = escape_like(search_term)
                like_pattern = f"%{escaped}%"
                query = query.filter(Document.document_number.like(like_pattern))

            # Total count before pagination
            total = query.count()

            # Order and paginate
            query = query.order_by(Document.date.desc())
            offset = (page - 1) * per_page
            docs = query.offset(offset).limit(per_page).all()

            # Build result list
            results = []
            for doc in docs:
                row = {
                    "id": doc.id,
                    "type": doc.type.upper() if doc.type else "",
                    "document_number": doc.document_number,
                    "date": doc.date,
                    "status": doc.status,
                    "username": doc.user.username if doc.user else "Unknown",
                    "entity_name": "",
                    "total_amount": None,
                }

                # Type-specific fields
                if isinstance(doc, Sale):
                    row["total_amount"] = doc.total_amount
                    row["entity_name"] = doc.customer.name if doc.customer else ""
                elif isinstance(doc, Purchase):
                    row["total_amount"] = doc.total_cost
                    row["entity_name"] = doc.supplier.company_name if doc.supplier else ""
                elif isinstance(doc, Proforma):
                    row["total_amount"] = doc.total_amount
                    row["entity_name"] = doc.customer.name if doc.customer else ""

                results.append(row)

            return {
                "documents": results,
                "total": total,
                "page": page,
            }

    @staticmethod
    def get_document_details(doc_id: int, doc_type: str) -> dict[str, Any] | None:
        """
        Get full document details with line items based on type.

        Args:
            doc_id: Document ID.
            doc_type: Document type string (sale, purchase, proforma).

        Returns:
            Dict with document header and items, or None.
        """
        db = Database()
        with db.get_session() as session:
            doc_type_lower = doc_type.lower()

            if doc_type_lower == "sale":
                return DocumentBrowserService._get_sale_details(session, doc_id)
            elif doc_type_lower == "purchase":
                return DocumentBrowserService._get_purchase_details(session, doc_id)
            elif doc_type_lower == "proforma":
                return DocumentBrowserService._get_proforma_details(session, doc_id)
            else:
                # Generic document
                doc = session.query(Document).filter_by(id=doc_id).first()
                if doc:
                    return {
                        "id": doc.id,
                        "document_number": doc.document_number,
                        "type": doc.type,
                        "date": doc.date,
                        "status": doc.status,
                        "username": doc.user.username if doc.user else "Unknown",
                        "items": [],
                        "payments": [],
                    }
                return None

    @staticmethod
    def _get_sale_details(session: Any, doc_id: int) -> dict[str, Any] | None:
        """Get sale details with items and payments."""
        sale = (
            session.query(Sale)
            .options(
                joinedload(Sale.items).joinedload(SaleItem.product),
                joinedload(Sale.payments),
                joinedload(Sale.customer),
                joinedload(Sale.user),
            )
            .filter_by(id=doc_id)
            .first()
        )
        if not sale:
            return None

        items = []
        for item in sale.items:
            items.append(
                {
                    "product_name": item.product.name_en if item.product else "Unknown",
                    "quantity": item.qty,
                    "unit_price": item.unit_price,
                    "discount_type": item.discount_type,
                    "discount_value": item.discount_value,
                    "line_total": item.subtotal,
                }
            )

        payments = []
        for p in sale.payments:
            payments.append({"method": p.payment_method, "amount": p.amount})

        return {
            "id": sale.id,
            "document_number": sale.document_number,
            "type": "sale",
            "date": sale.date,
            "status": sale.status,
            "username": sale.user.username if sale.user else "Unknown",
            "entity_name": sale.customer.name if sale.customer else "",
            "total_amount": sale.total_amount,
            "tax_vat": sale.tax_vat,
            "tax_sscl": sale.tax_sscl,
            "net_revenue": sale.net_revenue,
            "payment_method": sale.payment_method,
            "items": items,
            "payments": payments,
            "refund_of_sale_id": sale.refund_of_sale_id,
        }

    @staticmethod
    def _get_purchase_details(session: Any, doc_id: int) -> dict[str, Any] | None:
        """Get purchase details with items."""
        purchase = (
            session.query(Purchase)
            .options(
                joinedload(Purchase.items).joinedload(PurchaseItem.product),
                joinedload(Purchase.supplier),
                joinedload(Purchase.user),
            )
            .filter_by(id=doc_id)
            .first()
        )
        if not purchase:
            return None

        items = []
        for item in purchase.items:
            items.append(
                {
                    "product_name": item.product.name_en if item.product else "Unknown",
                    "quantity": item.qty_received,
                    "unit_price": item.unit_cost,
                    "discount_type": "NONE",
                    "discount_value": 0,
                    "line_total": item.qty_received * item.unit_cost,
                }
            )

        return {
            "id": purchase.id,
            "document_number": purchase.document_number,
            "type": "purchase",
            "date": purchase.date,
            "status": purchase.status,
            "username": purchase.user.username if purchase.user else "Unknown",
            "entity_name": purchase.supplier.company_name if purchase.supplier else "",
            "total_amount": purchase.total_cost,
            "items": items,
            "payments": [],
        }

    @staticmethod
    def _get_proforma_details(session: Any, doc_id: int) -> dict[str, Any] | None:
        """Get proforma details with items."""
        proforma = (
            session.query(Proforma)
            .options(
                joinedload(Proforma.items).joinedload(ProformaItem.product),
                joinedload(Proforma.customer),
                joinedload(Proforma.user),
            )
            .filter_by(id=doc_id)
            .first()
        )
        if not proforma:
            return None

        items = []
        for item in proforma.items:
            items.append(
                {
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "discount_type": item.discount_type,
                    "discount_value": item.discount_value,
                    "line_total": item.line_total,
                }
            )

        return {
            "id": proforma.id,
            "document_number": proforma.document_number,
            "type": "proforma",
            "date": proforma.date,
            "status": proforma.status,
            "username": proforma.user.username if proforma.user else "Unknown",
            "entity_name": proforma.customer.name if proforma.customer else "",
            "total_amount": proforma.total_amount,
            "tax_vat": proforma.tax_vat,
            "tax_sscl": proforma.tax_sscl,
            "validity_days": proforma.validity_days,
            "expiry_date": proforma.expiry_date,
            "converted_sale_id": proforma.converted_sale_id,
            "notes": proforma.notes,
            "items": items,
            "payments": [],
        }
