"""Tests for UnitService CRUD operations."""

import pytest
from cbpos.core.services.unit_service import UnitService
from cbpos.core.models import Unit, Product


class TestUnitService:
    """Unit tests for the UnitService."""

    def test_create_unit(self, db_session):
        """Test creating a new unit."""
        unit = UnitService.create(name="Kilogram", abbreviation="kg", decimal_places=3)
        assert unit.id is not None
        assert unit.name == "Kilogram"
        assert unit.abbreviation == "kg"
        assert unit.decimal_places == 3
        assert unit.is_active is True

    def test_create_duplicate_raises(self, db_session):
        """Test that creating a duplicate unit name raises ValueError."""
        UnitService.create(name="Piece", abbreviation="pcs")
        with pytest.raises(ValueError, match="already exists"):
            UnitService.create(name="Piece", abbreviation="pc")

    def test_get_all_active_only(self, db_session):
        """Test get_all returns only active units by default."""
        u1 = Unit(name="Active1", abbreviation="a1", is_active=True)
        u2 = Unit(name="Inactive1", abbreviation="i1", is_active=False)
        db_session.add_all([u1, u2])
        db_session.flush()

        units = UnitService.get_all(active_only=True)
        names = [u.name for u in units]
        assert "Active1" in names
        assert "Inactive1" not in names

    def test_get_all_including_inactive(self, db_session):
        """Test get_all with active_only=False returns all."""
        u1 = Unit(name="Active2", abbreviation="a2", is_active=True)
        u2 = Unit(name="Inactive2", abbreviation="i2", is_active=False)
        db_session.add_all([u1, u2])
        db_session.flush()

        units = UnitService.get_all(active_only=False)
        names = [u.name for u in units]
        assert "Active2" in names
        assert "Inactive2" in names

    def test_update_unit(self, db_session):
        """Test updating a unit."""
        unit = Unit(name="OldName", abbreviation="old", decimal_places=0)
        db_session.add(unit)
        db_session.flush()

        updated = UnitService.update(unit_id=unit.id, name="NewName", abbreviation="new", decimal_places=2)
        assert updated.name == "NewName"
        assert updated.abbreviation == "new"
        assert updated.decimal_places == 2

    def test_update_nonexistent_raises(self, db_session):
        """Test updating a non-existent unit raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            UnitService.update(unit_id=99999, name="X", abbreviation="x", decimal_places=0)

    def test_delete_unit_soft(self, db_session):
        """Test that delete performs soft delete (deactivation)."""
        unit = Unit(name="ToDelete", abbreviation="td", is_active=True)
        db_session.add(unit)
        db_session.flush()

        UnitService.delete(unit.id)
        db_session.refresh(unit)
        assert unit.is_active is False

    def test_delete_unit_with_products_raises(self, db_session):
        """Test that deleting a unit with products raises ValueError."""
        unit = Unit(name="InUse", abbreviation="iu", is_active=True)
        db_session.add(unit)
        db_session.flush()

        product = Product(
            name_en="Test Product",
            barcode="UNIT-TEST-001",
            price=100,
            stock_qty=10,
            unit_id=unit.id,
        )
        db_session.add(product)
        db_session.flush()

        with pytest.raises(ValueError, match="Cannot delete"):
            UnitService.delete(unit.id)
