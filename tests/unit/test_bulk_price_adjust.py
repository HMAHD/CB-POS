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
