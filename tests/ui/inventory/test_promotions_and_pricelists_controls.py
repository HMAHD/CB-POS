"""Tests for issue #595 (UI-028-C): Promotions On/Off column and visible Remove Override button in Price Lists."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from PyQt6.QtCore import Qt

from cbpos.core.models import PriceList, PriceListItem, Product, Promotion
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.promotion_view import PromotionView

pytestmark = pytest.mark.usefixtures("qapp")


def test_promotion_on_off_column_toggles_active_state(db_session, monkeypatch):
    """Promotions table should have an On/Off column that toggles is_active without context menu."""
    now = datetime.now()
    promo = Promotion(
        name="Flash Sale",
        type="PERCENTAGE",
        value=Decimal("15.00"),
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=1),
        is_active=True,
    )
    db_session.add(promo)
    db_session.commit()

    view = PromotionView()
    assert view.table.columnCount() == 8

    # Check On/Off column header
    header_label = view.table.horizontalHeaderItem(7).text()
    assert header_label in ("On/Off", "Active")

    # Row 0 check state
    item = view.table.item(0, 7)
    assert bool(item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
    assert item.checkState() == Qt.CheckState.Checked

    # Toggle off by changing check state
    item.setCheckState(Qt.CheckState.Unchecked)

    # Refresh promo from database
    db_session.expire_all()
    updated = db_session.get(Promotion, promo.id)
    assert updated.is_active is False

    view.close()
    view.deleteLater()


def test_pricelist_visible_remove_override_button(db_session, monkeypatch):
    """Price list view should have a visible remove override button enabled only when selected row has an override."""
    # Seed product and price list with override
    prod1 = Product(name_en="Widget A", barcode="1111", price=Decimal("100.00"), cost=Decimal("50.00"))
    prod2 = Product(name_en="Widget B", barcode="2222", price=Decimal("200.00"), cost=Decimal("100.00"))
    plist = PriceList(name="VIP List", is_active=True)
    db_session.add_all([prod1, prod2, plist])
    db_session.commit()

    item_override = PriceListItem(price_list_id=plist.id, product_id=prod1.id, price=Decimal("80.00"))
    db_session.add(item_override)
    db_session.commit()

    view = PriceListView()
    assert hasattr(view, "btn_remove_override")
    assert view.btn_remove_override.isVisibleTo(view) or view.btn_remove_override.parent() is not None

    # Select plist
    view._on_nav_clicked(plist)

    # Initially before selection, button is disabled
    view.table.clearSelection()
    view._on_table_selection_changed()
    assert not view.btn_remove_override.isEnabled()

    # Find row with Widget A (has override)
    row_with_override = None
    row_without_override = None
    for r in range(view.table.rowCount()):
        if int(view.table.item(r, 0).text()) == prod1.id:
            row_with_override = r
        elif int(view.table.item(r, 0).text()) == prod2.id:
            row_without_override = r

    assert row_with_override is not None
    assert row_without_override is not None

    # Select row with override -> button should be enabled
    view.table.selectRow(row_with_override)
    view._on_table_selection_changed()
    assert view.btn_remove_override.isEnabled()

    # Select row without override -> button should be disabled
    view.table.selectRow(row_without_override)
    view._on_table_selection_changed()
    assert not view.btn_remove_override.isEnabled()

    view.close()
    view.deleteLater()
