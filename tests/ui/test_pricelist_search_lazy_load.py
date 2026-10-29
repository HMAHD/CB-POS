"""Unit tests for PriceListView search filter and lazy loading (#543)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt

from cbpos.core.models import Product
from cbpos.ui.views.pricelist_view import BATCH_SIZE, PriceListView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _make_product(db_session, name: str, barcode: str | None = None, price: str = "100.00", cost: str = "50.00"):
    suffix = _next_suffix()
    bc = barcode or f"BC-{suffix}"
    p = Product(
        barcode=bc,
        name_en=name,
        price=Decimal(price),
        cost=Decimal(cost),
        is_active=True,
    )
    db_session.add(p)
    db_session.flush()
    return p


class TestPriceListSearchAndLazyLoading:
    def test_lazy_loading_first_batch_and_scroll_more(self, db_session):
        """When there are more products than BATCH_SIZE, only BATCH_SIZE are loaded initially.

        Scrolling or calling _load_more_items loads the next batch.
        """
        # Create 120 products
        for i in range(120):
            _make_product(db_session, f"Product {i:03d}")
        view = PriceListView()
        pl = view.price_list_service.create_price_list(f"Test List {_next_suffix()}")
        view.load_lists()
        view._on_nav_clicked(pl)

        assert len(view._all_products) == 120
        assert len(view._displayed_products) == 120
        # Table should only have BATCH_SIZE (50) rows initially
        assert view.table.rowCount() == BATCH_SIZE
        assert view._loaded_count == BATCH_SIZE
        assert "50" in view.lbl_count.text()
        assert "120" in view.lbl_count.text()

        # Load next batch
        view._load_more_items()
        assert view.table.rowCount() == 100
        assert view._loaded_count == 100

        # Load remaining batch
        view._load_more_items()
        assert view.table.rowCount() == 120
        assert view._loaded_count == 120

        # Further calls do nothing
        view._load_more_items()
        assert view.table.rowCount() == 120

    def test_search_by_name(self, db_session):
        """Searching filters products by name case-insensitively and updates counts."""
        _make_product(db_session, "Apple Juice", barcode="AJ-001")
        _make_product(db_session, "Banana Smoothie", barcode="BS-002")
        _make_product(db_session, "Apple Pie", barcode="AP-003")

        view = PriceListView()
        pl = view.price_list_service.create_price_list(f"Test List {_next_suffix()}")
        view.load_lists()
        view._on_nav_clicked(pl)

        # Search for "apple"
        view.search_input.setText("apple")
        assert len(view._displayed_products) == 2
        assert view.table.rowCount() == 2

        names = [view.table.item(r, 1).text() for r in range(view.table.rowCount())]
        assert "Apple Juice" in names
        assert "Apple Pie" in names
        assert "Banana Smoothie" not in names

        # Clear search
        view.search_input.setText("")
        assert len(view._displayed_products) == 3
        assert view.table.rowCount() == 3

    def test_search_by_barcode(self, db_session):
        """Searching filters products by barcode matching."""
        _make_product(db_session, "Item One", barcode="479123456001")
        _make_product(db_session, "Item Two", barcode="479123456002")

        view = PriceListView()
        pl = view.price_list_service.create_price_list(f"Test List {_next_suffix()}")
        view.load_lists()
        view._on_nav_clicked(pl)

        view.search_input.setText("56002")
        assert len(view._displayed_products) == 1
        assert view.table.rowCount() == 1
        assert view.table.item(0, 1).text() == "Item Two"

    def test_search_with_no_matches(self, db_session):
        """Searching with no matches shows 0 rows and 0 count gracefully."""
        _make_product(db_session, "Item One", barcode="111")
        view = PriceListView()
        pl = view.price_list_service.create_price_list(f"Test List {_next_suffix()}")
        view.load_lists()
        view._on_nav_clicked(pl)

        view.search_input.setText("nonexistent-query-xyz")
        assert len(view._displayed_products) == 0
        assert view.table.rowCount() == 0
        assert "0" in view.lbl_count.text()

    def test_switching_price_list_resets_search_and_pagination(self, db_session):
        """Switching to another price list clears the search input and resets pagination."""
        _make_product(db_session, "Product A", barcode="PA-1")
        _make_product(db_session, "Product B", barcode="PB-2")

        view = PriceListView()
        pl1 = view.price_list_service.create_price_list(f"List 1 {_next_suffix()}")
        pl2 = view.price_list_service.create_price_list(f"List 2 {_next_suffix()}")
        view.load_lists()

        view._on_nav_clicked(pl1)
        view.search_input.setText("Product A")
        assert len(view._displayed_products) == 1

        # Switch to pl2
        view._on_nav_clicked(pl2)
        assert view.search_input.text() == ""
        assert len(view._displayed_products) == 2
        assert view.table.rowCount() == 2

    def test_search_preserves_override_editing(self, db_session):
        """Overrides can be edited while a search filter is active."""
        p1 = _make_product(db_session, "Orange Cordial", price="200.00")
        view = PriceListView()
        pl = view.price_list_service.create_price_list(f"Test List {_next_suffix()}")
        view.load_lists()
        view._on_nav_clicked(pl)

        view.search_input.setText("Cordial")
        assert view.table.rowCount() == 1

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 1
        fake_dialog.get_price.return_value = Decimal("250.00")
        with patch("cbpos.ui.views.pricelist_view.SetItemPriceDialog", return_value=fake_dialog):
            view._edit_item_price_row(0)

        # Verify override in DB
        items = view.price_list_service.get_items(pl.id)
        assert len(items) == 1
        assert items[0].product_id == p1.id
        assert items[0].price == Decimal("250.00")
        assert view.table.rowCount() == 1
        assert view.table.item(0, 3).data(Qt.ItemDataRole.UserRole) == Decimal("250.00")
