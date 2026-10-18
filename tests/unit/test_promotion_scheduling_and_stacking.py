"""Unit tests for Promotion Scheduling and Stacking (#636).

Covers:
1. Daily recurring time windows (intra-day and overnight) in PricingService.
2. Price list stacking vs best-of modes in PricingService.
3. PromotionService validation, persistence, and overlap detection.
4. PromotionDialog UI fields, overlap banner, and stacking disclosure.
5. SalesTaxPage settings integration.
"""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QTime

from cbpos.core.database import Database
from cbpos.core.models import Customer, PriceList, PriceListItem, Product, Promotion
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.pricing_service import PricingService
from cbpos.core.services.promotion_service import PromotionService
from cbpos.ui.dialogs import promotion_dialog as promotion_dialog_module
from cbpos.ui.dialogs.promotion_dialog import PromotionDialog
from cbpos.ui.views.settings_pages.sales_tax import SalesTaxPage

pytestmark = pytest.mark.usefixtures("qapp")

_BARCODE_PREFIX = "SCHEDTEST-"


def _next_suffix() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture(autouse=True)
def _clean_test_rows(db_session):
    def _clean():
        with Database().get_session() as session:
            session.query(Customer).filter(Customer.name == "Gold Member").delete()
            session.query(PriceListItem).delete()
            session.query(PriceList).filter(PriceList.name == "Wholesale VIP").delete()
            session.query(Promotion).delete()
            session.query(Product).filter(Product.barcode.like(f"{_BARCODE_PREFIX}%")).delete(synchronize_session=False)

    _clean()
    yield
    _clean()


def _make_product(db_session, price="100.00", category_id=None):
    suffix = _next_suffix()
    p = Product(
        barcode=f"{_BARCODE_PREFIX}{suffix}",
        name_en=f"Product {suffix}",
        price=Decimal(price),
        category_id=category_id,
        is_active=True,
    )
    db_session.add(p)
    db_session.flush()
    return p


def _make_promotion(
    db_session,
    promo_type="PERCENTAGE",
    value="10",
    daily_start=None,
    daily_end=None,
    days_of_week=None,
    category_id=None,
    is_active=True,
):
    now = datetime.now()
    suffix = _next_suffix()
    promo = Promotion(
        name=f"Promo {suffix}",
        type=promo_type,
        value=Decimal(str(value)),
        start_time=now - timedelta(days=30),
        end_time=now + timedelta(days=30),
        daily_start=daily_start,
        daily_end=daily_end,
        days_of_week=days_of_week,
        category_id=category_id,
        is_active=is_active,
    )
    db_session.add(promo)
    db_session.flush()
    return promo


class TestDailyTimeWindowPricing:
    """PricingService respects daily time windows (intra-day and overnight)."""

    def test_intra_day_window_applies_inside_hours(self, db_session):
        product = _make_product(db_session, price="100.00")
        _make_promotion(
            db_session,
            promo_type="PERCENTAGE",
            value="20",
            daily_start=time(14, 0),
            daily_end=time(18, 0),
        )

        # 15:30 is inside window
        now = datetime(2026, 10, 17, 15, 30)
        result = PricingService.calculate_price(product, now=now)
        assert result["final_price"] == Decimal("80.00")
        assert "Promo" in result["applied_rule"]

    def test_intra_day_window_skips_outside_hours(self, db_session):
        product = _make_product(db_session, price="100.00")
        _make_promotion(
            db_session,
            promo_type="PERCENTAGE",
            value="20",
            daily_start=time(14, 0),
            daily_end=time(18, 0),
        )

        # 19:00 is outside window
        now = datetime(2026, 10, 17, 19, 0)
        result = PricingService.calculate_price(product, now=now)
        assert result["final_price"] == Decimal("100.00")
        assert result["applied_rule"] == "Standard Price"

    def test_overnight_window_applies_across_midnight(self, db_session):
        product = _make_product(db_session, price="100.00")
        _make_promotion(
            db_session,
            promo_type="PERCENTAGE",
            value="15",
            daily_start=time(22, 0),
            daily_end=time(4, 0),
        )

        # 23:00 is active
        now_night = datetime(2026, 10, 17, 23, 0)
        res_night = PricingService.calculate_price(product, now=now_night)
        assert res_night["final_price"] == Decimal("85.00")

        # 02:30 is active
        now_early = datetime(2026, 10, 18, 2, 30)
        res_early = PricingService.calculate_price(product, now=now_early)
        assert res_early["final_price"] == Decimal("85.00")

        # 12:00 midday is outside
        now_noon = datetime(2026, 10, 17, 12, 0)
        res_noon = PricingService.calculate_price(product, now=now_noon)
        assert res_noon["final_price"] == Decimal("100.00")


class TestPromotionStackingWithPriceLists:
    """PricingService evaluates stacking vs best-of mode based on ConfigService."""

    @pytest.fixture
    def setup_customer_and_price_list(self, db_session):
        pl = PriceList(
            name="Wholesale VIP",
            is_active=True,
            start_date=datetime.now() - timedelta(days=1),
            end_date=datetime.now() + timedelta(days=10),
        )
        db_session.add(pl)
        db_session.flush()

        customer = Customer(name="Gold Member", phone="0770000000", price_list_id=pl.id)
        db_session.add(customer)
        db_session.flush()

        product = _make_product(db_session, price="100.00")
        pli = PriceListItem(price_list_id=pl.id, product_id=product.id, price=Decimal("80.00"))
        db_session.add(pli)
        db_session.flush()

        return customer, product

    def test_best_of_mode_when_stacking_disabled_picks_price_list_if_cheaper(
        self, db_session, setup_customer_and_price_list
    ):
        customer, product = setup_customer_and_price_list
        # Promo is 10% off (100 -> 90), but price list is 80
        _make_promotion(db_session, promo_type="PERCENTAGE", value="10")

        with patch.object(ConfigService, "get", return_value=False):
            result = PricingService.calculate_price(product, customer=customer)
            assert result["final_price"] == Decimal("80.00")
            assert "Price List" in result["applied_rule"]

    def test_best_of_mode_when_stacking_disabled_picks_promo_if_cheaper(
        self, db_session, setup_customer_and_price_list
    ):
        customer, product = setup_customer_and_price_list
        # Promo is 30% off (100 -> 70), which beats price list 80
        _make_promotion(db_session, promo_type="PERCENTAGE", value="30")

        with patch.object(ConfigService, "get", return_value=False):
            result = PricingService.calculate_price(product, customer=customer)
            assert result["final_price"] == Decimal("70.00")
            assert "Promo" in result["applied_rule"]

    def test_stacking_enabled_applies_promo_on_top_of_price_list(self, db_session, setup_customer_and_price_list):
        customer, product = setup_customer_and_price_list
        # Promo is 10% off. Stacked on 80.00 -> 72.00
        _make_promotion(db_session, promo_type="PERCENTAGE", value="10")

        with patch.object(ConfigService, "get", return_value=True):
            result = PricingService.calculate_price(product, customer=customer)
            assert result["final_price"] == Decimal("72.00")
            assert "Price List" in result["applied_rule"]
            assert "Promo" in result["applied_rule"]


class TestPromotionServiceOverlapAndValidation:
    """PromotionService validates daily time windows and finds overlapping promotions."""

    def test_validate_rejects_single_time_in_daily_window(self, db_session):
        svc = PromotionService()
        with pytest.raises(ValueError, match="Both start and end time must be specified"):
            svc.validate_promotion("PERCENTAGE", Decimal("10"), daily_start=time(14, 0), daily_end=None)

    def test_validate_rejects_identical_daily_times(self, db_session):
        svc = PromotionService()
        with pytest.raises(ValueError, match="Daily start and end time cannot be identical"):
            svc.validate_promotion("PERCENTAGE", Decimal("10"), daily_start=time(14, 0), daily_end=time(14, 0))

    def test_create_and_update_with_daily_window(self, db_session):
        svc = PromotionService()
        now = datetime.now()
        promo = svc.create_promotion(
            name="Afternoon Delight",
            type="PERCENTAGE",
            value=Decimal("15"),
            start_time=now,
            end_time=now + timedelta(days=7),
            daily_start=time(14, 0),
            daily_end=time(17, 0),
        )
        assert promo.daily_start == time(14, 0)
        assert promo.daily_end == time(17, 0)

        updated = svc.update_promotion(
            promo.id,
            daily_start=time(15, 0),
            daily_end=time(18, 0),
        )
        assert updated.daily_start == time(15, 0)
        assert updated.daily_end == time(18, 0)

    def test_find_overlapping_matches_active_conflicts(self, db_session):
        svc = PromotionService()
        p1 = _make_promotion(
            db_session,
            promo_type="PERCENTAGE",
            value="10",
            daily_start=time(14, 0),
            daily_end=time(18, 0),
            days_of_week="0,1,2,3,4",
        )

        now = datetime.now()
        # Overlapping: same date range, overlapping daily window (16:00-20:00), weekday overlap
        overlaps = svc.find_overlapping(
            start_time=now,
            end_time=now + timedelta(days=2),
            days_of_week="1,2",
            daily_start=time(16, 0),
            daily_end=time(20, 0),
        )
        assert any(p.id == p1.id for p in overlaps)

    def test_find_overlapping_ignores_disjoint_daily_windows(self, db_session):
        svc = PromotionService()
        p1 = _make_promotion(
            db_session,
            promo_type="PERCENTAGE",
            value="10",
            daily_start=time(9, 0),
            daily_end=time(12, 0),
        )

        now = datetime.now()
        # Disjoint daily window: 14:00 to 18:00
        overlaps = svc.find_overlapping(
            start_time=now,
            end_time=now + timedelta(days=2),
            daily_start=time(14, 0),
            daily_end=time(18, 0),
        )
        assert not any(p.id == p1.id for p in overlaps)

    def test_find_overlapping_excludes_self_id(self, db_session):
        svc = PromotionService()
        p1 = _make_promotion(db_session)
        now = datetime.now()
        overlaps = svc.find_overlapping(
            start_time=now,
            end_time=now + timedelta(days=2),
            exclude_id=p1.id,
        )
        assert not any(p.id == p1.id for p in overlaps)


class TestPromotionDialogUI:
    """PromotionDialog daily window controls, overlap banner, and validation."""

    def test_dialog_daily_window_toggle_and_get_data(self, db_session):
        dialog = PromotionDialog()
        dialog.name_input.setText("Tea Break")
        dialog.value_input.setValue(10)

        # Initially daily window unchecked
        assert not dialog.chk_daily_window.isChecked()
        assert not dialog.daily_start_time.isEnabled()
        data = dialog.get_data()
        assert data["daily_start"] is None
        assert data["daily_end"] is None

        # Check daily window
        dialog.chk_daily_window.setChecked(True)
        assert dialog.daily_start_time.isEnabled()
        dialog.daily_start_time.setTime(QTime(15, 0))
        dialog.daily_end_time.setTime(QTime(17, 30))

        data = dialog.get_data()
        assert data["daily_start"] == time(15, 0)
        assert data["daily_end"] == time(17, 30)

    def test_dialog_rejects_daily_start_after_end(self, db_session):
        dialog = PromotionDialog()
        dialog.name_input.setText("Bad Time")
        dialog.value_input.setValue(10)
        dialog.chk_daily_window.setChecked(True)
        dialog.daily_start_time.setTime(QTime(18, 0))
        dialog.daily_end_time.setTime(QTime(14, 0))
        dialog.accept = MagicMock()

        with patch.object(promotion_dialog_module, "QMessageBox") as mock_box:
            dialog.validate_and_accept()
            mock_box.warning.assert_called_once()
            dialog.accept.assert_not_called()

    def test_dialog_displays_overlap_banner_when_conflict_exists(self, db_session):
        _make_promotion(db_session, promo_type="PERCENTAGE", value="20")
        dialog = PromotionDialog()
        dialog.check_overlap()

        assert not dialog.banner_overlap.isHidden()
        assert "⚠️" in dialog.banner_overlap.text()

    def test_dialog_shows_correct_stacking_disclosure(self, db_session):
        with patch.object(ConfigService, "get", return_value=True):
            dialog_stack = PromotionDialog()
            assert "stack" in dialog_stack.lbl_stacking_disclosure.text().lower()

        with patch.object(ConfigService, "get", return_value=False):
            dialog_best = PromotionDialog()
            assert "best-of" in dialog_best.lbl_stacking_disclosure.text().lower()


class TestSalesTaxSettingsStacking:
    """SalesTaxPage loads and saves promotion_stack_with_price_lists."""

    def test_sales_tax_page_loads_and_saves_stacking(self, db_session):
        page = SalesTaxPage()
        page.load({"promotion_stack_with_price_lists": True})
        assert page.chk_promo_stacking.isChecked()

        saved = page.save()
        assert saved["promotion_stack_with_price_lists"] is True

        with (
            patch("cbpos.ui.views.settings_pages.base.QMessageBox.question", return_value=16384),
            patch("cbpos.ui.views.settings_pages.base.QMessageBox.information"),
        ):
            page._reset_to_defaults()
        assert not page.chk_promo_stacking.isChecked()
