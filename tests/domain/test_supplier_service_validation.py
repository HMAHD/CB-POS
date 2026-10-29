"""
#522: SupplierService.create_supplier/update_supplier accepted blank fields
verbatim -- a blank company_name (unique, NOT NULL) or a second blank-string
phone (unique, nullable, but '' collides with another '') reached the DB's
UNIQUE constraint uncaught, crashing the whole app from a single click in
the Add Supplier dialog. Validates in the service layer as defense-in-depth
beneath the UI-level check, mirroring UnitService's create()/update()
duplicate-check pattern.
"""

import pytest

from cbpos.core.models import Supplier
from cbpos.core.services.supplier_service import SupplierService


class TestCreateSupplierValidation:
    def test_blank_company_name_raises(self, db_session):
        with pytest.raises(ValueError, match="required"):
            SupplierService.create_supplier(company_name="   ")

    def test_duplicate_company_name_raises(self, db_session):
        SupplierService.create_supplier(company_name="Acme Traders")
        with pytest.raises(ValueError, match="already exists"):
            SupplierService.create_supplier(company_name="Acme Traders")

    def test_two_blank_phones_do_not_collide(self, db_session):
        """Blank phone must normalize to NULL, not '', so a second supplier
        with no phone doesn't hit the unique constraint (the original crash)."""
        SupplierService.create_supplier(company_name="Supplier A", phone="")
        SupplierService.create_supplier(company_name="Supplier B", phone="")

        db_session.expire_all()
        suppliers = db_session.query(Supplier).filter(Supplier.company_name.in_(["Supplier A", "Supplier B"])).all()
        assert len(suppliers) == 2
        assert all(s.phone is None for s in suppliers)

    def test_duplicate_phone_raises(self, db_session):
        SupplierService.create_supplier(company_name="Supplier A", phone="0711234567")
        with pytest.raises(ValueError, match="already exists"):
            SupplierService.create_supplier(company_name="Supplier B", phone="0711234567")

    def test_blank_optional_fields_are_stored_as_none(self, db_session):
        supplier = SupplierService.create_supplier(company_name="Minimal Supplier", contact_person="  ", email="  ")
        assert supplier.contact_person is None
        assert supplier.email is None


class TestUpdateSupplierValidation:
    def test_blank_company_name_raises(self, db_session):
        supplier = SupplierService.create_supplier(company_name="Original Name")
        with pytest.raises(ValueError, match="required"):
            SupplierService.update_supplier(supplier.id, company_name="   ")

    def test_renaming_to_another_suppliers_name_raises(self, db_session):
        SupplierService.create_supplier(company_name="Existing Co")
        target = SupplierService.create_supplier(company_name="Renamable Co")
        with pytest.raises(ValueError, match="already exists"):
            SupplierService.update_supplier(target.id, company_name="Existing Co")

    def test_can_keep_its_own_name_unchanged(self, db_session):
        supplier = SupplierService.create_supplier(company_name="Stable Co")
        updated = SupplierService.update_supplier(supplier.id, company_name="Stable Co", phone="0709998888")
        assert updated.company_name == "Stable Co"
        assert updated.phone == "0709998888"

    def test_deactivate_via_is_active_flag(self, db_session):
        supplier = SupplierService.create_supplier(company_name="Soon Inactive Co")
        SupplierService.update_supplier(supplier.id, is_active=False)

        db_session.expire_all()
        assert db_session.get(Supplier, supplier.id).is_active is False
        assert supplier.id not in [s.id for s in SupplierService.get_all_suppliers()]
