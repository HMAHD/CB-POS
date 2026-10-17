from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from cbpos.core.models import Category, PriceList, PriceListItem, Product, User
from cbpos.core.services.price_list_service import (
    BulkAdjustmentRule,
    PriceListService,
)


@pytest.fixture
def sample_catalog(db_session: Session):
    cat_bev = Category(name="Beverages")
    cat_snack = Category(name="Snacks")
    db_session.add_all([cat_bev, cat_snack])
    db_session.flush()

    p1 = Product(
        barcode="B101",
        name_en="Coffee Beans",
        category_id=cat_bev.id,
        cost=Decimal("600.00"),
        price=Decimal("1000.00"),
        is_active=True,
    )
    p2 = Product(
        barcode="B102",
        name_en="Green Tea",
        category_id=cat_bev.id,
        cost=Decimal("400.00"),
        price=Decimal("500.00"),
        is_active=True,
    )
    p3 = Product(
        barcode="B103",
        name_en="Potato Chips",
        category_id=cat_snack.id,
        cost=Decimal("150.00"),
        price=Decimal("200.00"),
        is_active=True,
    )
    p4 = Product(
        barcode="B104",
        name_en="Gift Wrap Service",
        category_id=cat_snack.id,
        cost=Decimal("0.00"),
        price=Decimal("100.00"),
        is_active=True,
    )
    user = User(username="admin_user", pin_hash="dummy")
    db_session.add_all([p1, p2, p3, p4, user])
    db_session.flush()

    pl = PriceList(name="New Year Promo", is_active=True)
    db_session.add(pl)
    db_session.flush()

    # Pre-existing override on p1
    item1 = PriceListItem(price_list_id=pl.id, product_id=p1.id, price=Decimal("950.00"))
    db_session.add(item1)
    db_session.commit()

    return {
        "price_list": pl,
        "categories": [cat_bev, cat_snack],
        "products": [p1, p2, p3, p4],
        "user": user,
    }


def test_percentage_discount_calculation(sample_catalog):
    service = PriceListService()
    pl = sample_catalog["price_list"]
    rule = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("10.0"),  # 10% off
        rounding="EXACT",
        scope="ALL",
    )
    preview = service.calculate_preview(pl.id, rule)
    assert len(preview) == 4

    p1_item = next(it for it in preview if it.product_id == sample_catalog["products"][0].id)
    # Base 1000.00 - 10% = 900.00
    assert p1_item.new_list_price == Decimal("900.00")
    assert p1_item.base_price == Decimal("1000.00")
    assert p1_item.old_list_price == Decimal("950.00")
    assert not p1_item.is_below_cost
    assert p1_item.cost == Decimal("600.00")


def test_fixed_discount_calculation_and_zero_clamping(sample_catalog):
    service = PriceListService()
    pl = sample_catalog["price_list"]
    rule = BulkAdjustmentRule(
        rule_type="FIXED_OFF",
        value=Decimal("150.00"),  # Rs. 150 off base price
        rounding="EXACT",
        scope="ALL",
    )
    preview = service.calculate_preview(pl.id, rule)

    # p1: 1000 - 150 = 850
    p1_item = next(it for it in preview if it.product_id == sample_catalog["products"][0].id)
    assert p1_item.new_list_price == Decimal("850.00")

    # p4: 100 - 150 = clamped to 0.00
    p4_item = next(it for it in preview if it.product_id == sample_catalog["products"][3].id)
    assert p4_item.new_list_price == Decimal("0.00")


def test_fixed_markup_calculation(sample_catalog):
    service = PriceListService()
    pl = sample_catalog["price_list"]
    rule = BulkAdjustmentRule(
        rule_type="FIXED_MARKUP",
        value=Decimal("50.00"),  # Rs. 50 above base price
        rounding="EXACT",
        scope="ALL",
    )
    preview = service.calculate_preview(pl.id, rule)

    p1_item = next(it for it in preview if it.product_id == sample_catalog["products"][0].id)
    assert p1_item.new_list_price == Decimal("1050.00")


def test_margin_over_cost_calculation(sample_catalog):
    service = PriceListService()
    pl = sample_catalog["price_list"]
    rule = BulkAdjustmentRule(
        rule_type="MARGIN_OVER_COST",
        value=Decimal("25.0"),  # Cost + 25%
        rounding="EXACT",
        scope="ALL",
    )
    preview = service.calculate_preview(pl.id, rule)

    # p1: cost 600 * 1.25 = 750.00
    p1_item = next(it for it in preview if it.product_id == sample_catalog["products"][0].id)
    assert p1_item.new_list_price == Decimal("750.00")

    # p4: cost 0.00 falls back to base price 100.00
    p4_item = next(it for it in preview if it.product_id == sample_catalog["products"][3].id)
    assert p4_item.new_list_price == Decimal("100.00")
    assert p4_item.margin_percent is None


def test_rounding_modes(sample_catalog):
    service = PriceListService()
    pl = sample_catalog["price_list"]

    # 13% off 1000 = 870.00, 13% off 500 = 435.00, 13% off 200 = 174.00
    # Let's test 13.5% off 500 = 432.50
    rule_exact = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("13.5"),
        rounding="EXACT",
        scope="SELECTED",
        product_ids=[sample_catalog["products"][1].id],  # base 500
    )
    preview_exact = service.calculate_preview(pl.id, rule_exact)
    assert preview_exact[0].new_list_price == Decimal("432.50")

    # Nearest Rupee: 432.50 -> 433.00 (ROUND_HALF_UP)
    rule_n1 = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("13.5"),
        rounding="NEAREST_1",
        scope="SELECTED",
        product_ids=[sample_catalog["products"][1].id],
    )
    preview_n1 = service.calculate_preview(pl.id, rule_n1)
    assert preview_n1[0].new_list_price == Decimal("433.00")

    # Nearest 5: 432.50 -> 435.00
    rule_n5 = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("13.5"),
        rounding="NEAREST_5",
        scope="SELECTED",
        product_ids=[sample_catalog["products"][1].id],
    )
    preview_n5 = service.calculate_preview(pl.id, rule_n5)
    assert preview_n5[0].new_list_price == Decimal("435.00")

    # Charm .99: 432.50 -> 432.99
    rule_charm = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("13.5"),
        rounding="CHARM_99",
        scope="SELECTED",
        product_ids=[sample_catalog["products"][1].id],
    )
    preview_charm = service.calculate_preview(pl.id, rule_charm)
    assert preview_charm[0].new_list_price == Decimal("432.99")


def test_below_cost_warning_detection(sample_catalog):
    service = PriceListService()
    pl = sample_catalog["price_list"]
    # 50% discount on Green Tea (Base 500 -> 250, but Cost is 400)
    rule = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("50.0"),
        rounding="EXACT",
        scope="SELECTED",
        product_ids=[sample_catalog["products"][1].id],
    )
    preview = service.calculate_preview(pl.id, rule)
    tea = preview[0]
    assert tea.new_list_price == Decimal("250.00")
    assert tea.is_below_cost
    assert tea.loss_amount == Decimal("150.00")


def test_scope_filtering(sample_catalog):
    service = PriceListService()
    pl = sample_catalog["price_list"]
    cat_bev = sample_catalog["categories"][0]

    # Category scope
    rule_cat = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("5.0"),
        rounding="EXACT",
        scope="CATEGORY",
        category_id=cat_bev.id,
    )
    preview_cat = service.calculate_preview(pl.id, rule_cat)
    # Only 2 beverages
    assert len(preview_cat) == 2
    assert all(it.category_name == "Beverages" for it in preview_cat)

    # Selected scope
    p1 = sample_catalog["products"][0]
    rule_sel = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("5.0"),
        rounding="EXACT",
        scope="SELECTED",
        product_ids=[p1.id],
    )
    preview_sel = service.calculate_preview(pl.id, rule_sel)
    assert len(preview_sel) == 1
    assert preview_sel[0].product_id == p1.id


def test_atomic_bulk_apply_and_single_audit_entry(sample_catalog, db_session, monkeypatch):
    from cbpos.core.constants.audit import PRICE_LIST_BULK_ADJUST, PRICING_EVENT
    from cbpos.core.models import AuditLog
    from cbpos.core.services.auth_service import AuthService

    monkeypatch.setattr(AuthService, "get_current_user", lambda: sample_catalog["user"])

    service = PriceListService()
    pl = sample_catalog["price_list"]
    rule = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("15.0"),
        rounding="NEAREST_1",
        scope="ALL",
    )
    preview = service.calculate_preview(pl.id, rule)
    count = service.apply_bulk_adjust(pl.id, preview, rule_summary="15% off base price, nearest rupee")
    assert count == 4

    # Check that database items have new prices
    items = service.get_items(pl.id)
    assert len(items) == 4
    # p1 (Coffee Beans: base 1000 - 15% = 850)
    p1_item = next(it for it in items if it.product_id == sample_catalog["products"][0].id)
    assert p1_item.price == Decimal("850.00")

    # Master product base price and cost must remain completely untouched!
    for p in sample_catalog["products"]:
        db_p = db_session.get(Product, p.id)
        assert db_p.price == p.price
        assert db_p.cost == p.cost

    # Check exactly 1 audit entry for PRICE_LIST_BULK_ADJUST
    audit_entries = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == PRICING_EVENT,
            AuditLog.action == PRICE_LIST_BULK_ADJUST,
        )
        .all()
    )
    assert len(audit_entries) == 1
    entry = audit_entries[0]
    import json

    data = json.loads(entry.details)
    assert data["subject"] == pl.name
    assert "15%" in entry.details or "items_updated" in entry.details


def test_apply_bulk_adjust_rollback_on_error(sample_catalog, monkeypatch):
    service = PriceListService()
    pl = sample_catalog["price_list"]
    rule = BulkAdjustmentRule(
        rule_type="PERCENTAGE_OFF",
        value=Decimal("20.0"),
        rounding="EXACT",
        scope="ALL",
    )
    preview = service.calculate_preview(pl.id, rule)

    # Force an error during commit to verify rollback
    from unittest.mock import patch

    with patch(
        "cbpos.core.services.logging_service.LoggingService.add_change", side_effect=RuntimeError("DB Disk Failure")
    ):
        with pytest.raises(RuntimeError, match="DB Disk Failure"):
            service.apply_bulk_adjust(pl.id, preview, rule_summary="20% off")

    # Verify original override price on p1 is unchanged (950.00)
    items = service.get_items(pl.id)
    p1_item = next(it for it in items if it.product_id == sample_catalog["products"][0].id)
    assert p1_item.price == Decimal("950.00")


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_bulk_adjust_i18n_keys_exist(lang):
    from cbpos.i18n import translate_in

    keys = [
        "pricelist.btn_bulk_adjust",
        "pricelist.bulk_title",
        "pricelist.bulk_target_scope",
        "pricelist.scope_selected",
        "pricelist.scope_category",
        "pricelist.scope_all",
        "pricelist.bulk_pricing_rule",
        "pricelist.rule_percent_off",
        "pricelist.rule_fixed_off",
        "pricelist.rule_fixed_markup",
        "pricelist.rule_margin_cost",
        "pricelist.bulk_adjustment_value",
        "pricelist.bulk_rounding_options",
        "pricelist.rounding_exact",
        "pricelist.rounding_nearest_1",
        "pricelist.rounding_nearest_5",
        "pricelist.rounding_charm_99",
        "pricelist.below_cost_warning_title",
        "pricelist.below_cost_warning_msg",
        "pricelist.below_cost_confirm_title",
        "pricelist.below_cost_confirm_msg",
        "pricelist.margin_badge_safe",
        "pricelist.margin_badge_below_cost",
        "pricelist.cost_not_set",
        "pricelist.preview_title",
        "pricelist.btn_apply_adjustments",
    ]
    for key in keys:
        val = translate_in(lang, key)
        assert val != key, f"Missing translation for key '{key}' in '{lang}'"


class TestBulkPriceAdjustDialogUI:
    """Test suite for BulkPriceAdjustDialog widget interaction (#544)."""

    def test_dialog_init_with_no_selection(self, db_session, qapp):
        cat = Category(name="Snacks")
        db_session.add(cat)
        db_session.flush()

        p1 = Product(
            barcode="UI-B1", name_en="Chips", price=Decimal("100.00"), cost=Decimal("60.00"), category_id=cat.id
        )
        db_session.add(p1)
        db_session.commit()

        service = PriceListService()
        pl = service.create_price_list("Holiday Deals")

        from cbpos.ui.dialogs.bulk_price_adjust_dialog import BulkPriceAdjustDialog

        dialog = BulkPriceAdjustDialog(
            price_list_id=pl.id,
            price_list_name=pl.name,
            selected_product_ids=[],
        )

        assert not dialog.radio_selected.isEnabled()
        assert dialog.radio_all.isChecked()
        assert dialog.table_preview.rowCount() >= 1

    def test_dialog_init_with_selected_products(self, db_session, qapp):
        p1 = Product(barcode="UI-B2", name_en="Juice", price=Decimal("150.00"), cost=Decimal("90.00"))
        p2 = Product(barcode="UI-B3", name_en="Water", price=Decimal("50.00"), cost=Decimal("30.00"))
        db_session.add_all([p1, p2])
        db_session.commit()

        service = PriceListService()
        pl = service.create_price_list("Beverage Promo")

        from cbpos.ui.dialogs.bulk_price_adjust_dialog import BulkPriceAdjustDialog

        dialog = BulkPriceAdjustDialog(
            price_list_id=pl.id,
            price_list_name=pl.name,
            selected_product_ids=[p1.id],
        )

        assert dialog.radio_selected.isEnabled()
        assert dialog.radio_selected.isChecked()
        # Preview must contain only the 1 selected item
        assert dialog.table_preview.rowCount() == 1
        assert dialog.table_preview.item(0, 0).text() == "Juice"

    def test_dialog_below_cost_banner_and_apply(self, db_session, qapp):
        from unittest.mock import patch

        from PyQt6.QtWidgets import QMessageBox

        p1 = Product(barcode="UI-B4", name_en="Expensive Tea", price=Decimal("200.00"), cost=Decimal("120.00"))
        db_session.add(p1)
        db_session.commit()

        service = PriceListService()
        pl = service.create_price_list("Clearance")

        from cbpos.ui.dialogs.bulk_price_adjust_dialog import (
            RULE_FIXED_OFF,
            BulkPriceAdjustDialog,
        )

        dialog = BulkPriceAdjustDialog(
            price_list_id=pl.id,
            price_list_name=pl.name,
            selected_product_ids=[p1.id],
        )

        # Set rule: 150 Rs off (New price: 200 - 150 = 50, cost is 120 -> below cost!)
        idx = dialog.combo_rule_type.findData(RULE_FIXED_OFF)
        dialog.combo_rule_type.setCurrentIndex(idx)
        dialog.spin_value.setValue(150.00)

        assert dialog.below_cost_count == 1
        assert not dialog.banner_below_cost.isHidden()
        assert "below purchase cost" in dialog.banner_below_cost.text()

        # Test apply: if user cancels prompt, should not accept
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No):
            with patch.object(dialog, "accept") as mock_accept:
                dialog.apply_and_accept()
                mock_accept.assert_not_called()

        # Test apply: if user confirms prompt, should persist and accept
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(dialog, "accept") as mock_accept:
                dialog.apply_and_accept()
                mock_accept.assert_called_once()

        # Verify saved in DB
        items = service.get_items(pl.id)
        saved = next(it for it in items if it.product_id == p1.id)
        assert saved.price == Decimal("50.00")

    def test_pricelist_view_bulk_adjust_button(self, db_session, qapp):
        from unittest.mock import patch

        from cbpos.ui.views.pricelist_view import PriceListView

        view = PriceListView()
        assert hasattr(view, "btn_bulk_adjust")
        assert view.btn_bulk_adjust.text() != ""

        # Test open dialog callback
        service = PriceListService()
        pl = service.create_price_list("Button Test List")
        view.current_list = pl

        with patch("cbpos.ui.views.pricelist_view.BulkPriceAdjustDialog") as mock_dlg_cls:
            mock_dlg = mock_dlg_cls.return_value
            mock_dlg.exec.return_value = False
            view.open_bulk_adjust_dialog()
            mock_dlg_cls.assert_called_once()
