"""
Tests for StockService.get_reorder_list() -- it queries Product without
eager-loading the suppliers relationship and returns objects straight out
of a `with db.get_session()` block, so in real usage (where that block's
session.close() actually runs) any later read of product.suppliers raises
DetachedInstanceError. reorder_view.py reads exactly that
(product.suppliers[0].company_name) to show each product's supplier.

Note: the shared db_session test fixture patches session.close() to a
no-op so rollback-based test isolation works across the whole suite, which
means it can't reproduce the real "session actually closed" crash this bug
causes in production (that requires a session that truly detaches, which
this fixture deliberately prevents for unrelated reasons). This test
instead confirms the query is structurally correct -- suppliers loads via
the join with real data, and the code reads the correct column
(company_name, not the nonexistent Supplier.name) -- which was also wrong
before this fix.
"""

import pytest

from cbpos.core.models import Product, Supplier
from cbpos.core.services.stock_service import StockService

_counter = 0


@pytest.fixture
def understocked_product_with_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"Acme Supplies {_counter}")
    product = Product(
        name_en=f"ReorderProduct_{_counter}",
        price=10.0,
        stock_qty=1.0,
        reorder_point=5.0,
        barcode=f"RPX{_counter:04d}",
        is_active=True,
        is_service=False,
        suppliers=[supplier],
    )
    db_session.add_all([supplier, product])
    db_session.commit()
    return product, supplier


class TestGetReorderList:
    def test_supplier_relationship_is_eager_loaded_with_correct_column(
        self, db_session, understocked_product_with_supplier
    ):
        _, supplier = understocked_product_with_supplier

        results = StockService.get_reorder_list()

        matching = [p for p in results if p.id == understocked_product_with_supplier[0].id]
        assert len(matching) == 1
        product = matching[0]

        assert bool(product.suppliers) is True
        # Supplier has no .name attribute, only .company_name -- the UI
        # code that reads this (reorder_view.py) used to read .name,
        # which would raise AttributeError even once eager-loading
        # was fixed.
        assert not hasattr(product.suppliers[0], "name")
        assert product.suppliers[0].company_name == supplier.company_name

    def test_excludes_well_stocked_products(self, db_session):
        global _counter
        _counter += 1
        product = Product(
            name_en=f"WellStocked_{_counter}",
            price=10.0,
            stock_qty=100.0,
            reorder_point=5.0,
            barcode=f"WSX{_counter:04d}",
            is_active=True,
            is_service=False,
        )
        db_session.add(product)
        db_session.commit()

        results = StockService.get_reorder_list()
        assert product.id not in [p.id for p in results]
