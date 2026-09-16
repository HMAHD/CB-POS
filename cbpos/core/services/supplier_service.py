import logging

from sqlalchemy import select

from cbpos.core.database import Database
from cbpos.core.models import Supplier
from cbpos.core.utils.formatters import escape_like

logger = logging.getLogger(__name__)


class SupplierService:
    """
    Service for managing suppliers.
    """

    @staticmethod
    def create_supplier(
        company_name: str,
        phone: str | None = None,
        contact_person: str | None = None,
        email: str | None = None,
        address: str | None = None,
        tax_number: str | None = None,
        contact_details: str | None = None,
        payment_terms: int = 0,
    ) -> Supplier:
        """
        Create a new supplier.
        """
        db = Database()
        with db.get_session() as session:
            supplier = Supplier(
                company_name=company_name,
                phone=phone,
                contact_person=contact_person,
                email=email,
                address=address,
                tax_number=tax_number,
                contact_details=contact_details,
                payment_terms=payment_terms,
            )
            session.add(supplier)
            session.commit()
            session.refresh(supplier)
            return supplier

    @staticmethod
    def update_supplier(
        supplier_id: int,
        company_name: str | None = None,
        phone: str | None = None,
        contact_person: str | None = None,
        email: str | None = None,
        address: str | None = None,
        tax_number: str | None = None,
        contact_details: str | None = None,
        payment_terms: int | None = None,
        is_active: bool | None = None,
    ) -> Supplier | None:
        """
        Update an existing supplier.
        """
        db = Database()
        with db.get_session() as session:
            supplier = session.get(Supplier, supplier_id)
            if not supplier:
                return None

            if company_name is not None:
                supplier.company_name = company_name
            if phone is not None:
                supplier.phone = phone
            if contact_person is not None:
                supplier.contact_person = contact_person
            if email is not None:
                supplier.email = email
            if address is not None:
                supplier.address = address
            if tax_number is not None:
                supplier.tax_number = tax_number
            if contact_details is not None:
                supplier.contact_details = contact_details
            if payment_terms is not None:
                supplier.payment_terms = payment_terms
            if is_active is not None:
                supplier.is_active = is_active

            session.commit()
            session.refresh(supplier)
            return supplier

    @staticmethod
    def get_all_suppliers(active_only: bool = True) -> list[Supplier]:
        """
        Get all suppliers.
        """
        db = Database()
        with db.get_session() as session:
            stmt = select(Supplier)
            if active_only:
                stmt = stmt.where(Supplier.is_active.is_(True))
            return list(session.scalars(stmt).all())

    @staticmethod
    def search_suppliers(query: str) -> list[Supplier]:
        """
        Search suppliers by name, phone, or contact person.
        """
        db = Database()
        with db.get_session() as session:
            safe_query = escape_like(query)
            stmt = select(Supplier).where(
                (Supplier.company_name.ilike(f"%{safe_query}%"))
                | (Supplier.phone.ilike(f"%{safe_query}%"))
                | (Supplier.contact_person.ilike(f"%{safe_query}%"))
            )
            return list(session.scalars(stmt).all())

    @staticmethod
    def get_supplier_by_id(supplier_id: int) -> Supplier | None:
        """
        Get a supplier by ID.
        """
        db = Database()
        with db.get_session() as session:
            return session.get(Supplier, supplier_id)
