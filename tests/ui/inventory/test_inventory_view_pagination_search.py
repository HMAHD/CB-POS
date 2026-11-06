import itertools
from decimal import Decimal

import pytest

from cbpos.core.models import Product
from cbpos.i18n import _t
from cbpos.ui.views.inventory_view import InventoryView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = itertools.count(1)


def _next_suffix():
    return f"{next(_counter):04d}"


class TestInventoryViewPaginationAndSearch:
    def test_inventory_view_displays_100_products_per_page(self, db_session):
        """#863: InventoryView pages at 100 products per page with server-side count."""
        suffix = _next_suffix()
        products_data = [
            {
                "barcode": f"PG-{suffix}-{i:04d}",
                "name_en": f"Paged Item {suffix} {i:04d}",
                "price": Decimal("50.00"),
                "cost": Decimal("25.00"),
                "stock_qty": Decimal("10.000"),
                "is_active": True,
                "is_service": False,
            }
            for i in range(1, 251)
        ]
        db_session.bulk_insert_mappings(Product, products_data)
        db_session.commit()

        view = InventoryView()
        assert view.model.rowCount() == 100
        assert view.pagination._total_items >= 250
        assert "1\u2013100" in view.pagination._info_label.text()

        # Navigate to page 2 (index 1)
        view.pagination._go_next()
        assert view.model.rowCount() == 100
        assert "101\u2013200" in view.pagination._info_label.text()

        # Navigate to page 3 (index 2)
        view.pagination._go_next()
        assert view.model.rowCount() >= 50
        assert "201\u2013" in view.pagination._info_label.text()

    def test_inventory_view_search_debounced_and_empty_state(self, db_session):
        """#863: Search displays matching items or honest no_match empty state."""
        suffix = _next_suffix()
        p = Product(
            barcode=f"SRCH-{suffix}",
            name_en=f"Specific Search Target {suffix}",
            price=Decimal("150.00"),
            cost=Decimal("75.00"),
            stock_qty=Decimal("5.000"),
            is_active=True,
        )
        db_session.add(p)
        db_session.commit()

        view = InventoryView()

        # Type search query and trigger debounce
        view.search_input.setText(f"Specific Search Target {suffix}")
        view._search_timer.timeout.emit()

        assert view.model.rowCount() == 1
        assert view.model.products[0].barcode == f"SRCH-{suffix}"
        assert view.table_stack.currentIndex() == 0

        # Non-matching search shows honest empty state
        view.search_input.setText(f"NON_EXISTENT_PROD_{suffix}")
        view._search_timer.timeout.emit()

        assert view.model.rowCount() == 0
        assert view.table_stack.currentIndex() == 1
        expected_msg = _t("inventory.no_match", query=f"NON_EXISTENT_PROD_{suffix}")
        assert view.empty_label.text() == expected_msg

    def test_inventory_view_search_trilingual(self, db_session):
        """#863: Search matches Sinhala and Tamil names in InventoryView."""
        suffix = _next_suffix()
        p = Product(
            barcode=f"TRI-UI-{suffix}",
            name_en=f"Trilingual Rice {suffix}",
            name_si="සුවඳැල් සහල්",
            name_ta="சுவையான அரிசி",
            price=Decimal("300.00"),
            cost=Decimal("200.00"),
            stock_qty=Decimal("15.000"),
            is_active=True,
        )
        db_session.add(p)
        db_session.commit()

        view = InventoryView()

        # Sinhala search
        view.filter_data("සුවඳැල්")
        assert any(prod.barcode == f"TRI-UI-{suffix}" for prod in view.model.products)

        # Tamil search
        view.filter_data("சுவையான")
        assert any(prod.barcode == f"TRI-UI-{suffix}" for prod in view.model.products)
