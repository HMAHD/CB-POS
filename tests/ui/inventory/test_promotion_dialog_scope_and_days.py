"""
#310: the Create Promotion dialog had no product/category targeting at
all -- every promotion was necessarily store-wide, and "days of week"
was unstructured free text with no format validation. Added a category
scope combo (backed by a new nullable Promotion.category_id) and 7
day-of-week checkboxes replacing the free-text field.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import Category
from cbpos.core.services.promotion_service import PromotionService
from cbpos.ui.views.promotion_view import PromotionDialog

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_category(db_session):
    cat = Category(name=f"TestCat_{_next_suffix()}", color="#FF0000")
    db_session.add(cat)
    db_session.flush()
    return cat


class TestCategoryScopeCombo:
    def test_lists_all_products_first_then_every_category(self, db_session, test_category):
        dialog = PromotionDialog()
        assert dialog.category_combo.itemData(0) is None
        category_ids = [dialog.category_combo.itemData(i) for i in range(1, dialog.category_combo.count())]
        assert test_category.id in category_ids

    def test_get_data_reports_none_for_all_products(self, db_session):
        dialog = PromotionDialog()
        dialog.name_input.setText("Store Wide")
        data = dialog.get_data()
        assert data["category_id"] is None

    def test_get_data_reports_the_selected_category(self, db_session, test_category):
        dialog = PromotionDialog()
        dialog.name_input.setText("Category Scoped")
        index = dialog.category_combo.findData(test_category.id)
        dialog.category_combo.setCurrentIndex(index)

        data = dialog.get_data()
        assert data["category_id"] == test_category.id

    def test_prefills_the_promotions_existing_category(self, db_session, test_category):
        service = PromotionService()
        now = datetime.now()
        promo = service.create_promotion(
            name=f"Scoped_{_next_suffix()}",
            type="PERCENTAGE",
            value=Decimal("5.00"),
            start_time=now,
            end_time=now + timedelta(days=1),
            category_id=test_category.id,
        )

        dialog = PromotionDialog(promotion=promo)
        assert dialog.category_combo.currentData() == test_category.id


class TestDayCheckboxSerialization:
    def test_all_days_checked_serializes_to_none(self, db_session):
        dialog = PromotionDialog()
        dialog.name_input.setText("Every Day")
        for cb in dialog.day_checkboxes:
            cb.setChecked(True)

        data = dialog.get_data()
        assert data["days_of_week"] is None

    def test_unchecking_weekend_serializes_to_weekday_indices(self, db_session):
        dialog = PromotionDialog()
        dialog.name_input.setText("Weekdays Only")
        # Indices 5, 6 are Sat, Sun per _DAY_KEYS ordering.
        dialog.day_checkboxes[5].setChecked(False)
        dialog.day_checkboxes[6].setChecked(False)

        data = dialog.get_data()
        assert data["days_of_week"] == "0,1,2,3,4"
