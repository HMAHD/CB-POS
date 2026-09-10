"""
#308: PromotionView could only ever create a promotion -- no edit,
delete, or deactivate action existed anywhere (the table had
NoEditTriggers and no double-click/right-click wiring at all).

#309: STATUS was read straight from the stored is_active flag, which is
only ever set True at creation and never re-evaluated -- every
promotion showed "Active" forever regardless of its date range. Status
must now be computed live against start_time/end_time.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.i18n import _t
from cbpos.ui.views import promotion_view as promotion_view_module
from cbpos.ui.views.promotion_view import PromotionDialog, PromotionView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _create(view, name=None, start=None, end=None, is_active=True):
    now = datetime.now()
    promo = view.promotion_service.create_promotion(
        name=name or f"Promo_{_next_suffix()}",
        type="PERCENTAGE",
        value=Decimal("10.00"),
        start_time=start or now - timedelta(days=1),
        end_time=end or now + timedelta(days=7),
    )
    if not is_active:
        promo = view.promotion_service.update_promotion(promo.id, is_active=False)
    return promo


def _row_for(view, promo_id):
    for r in range(view.table.rowCount()):
        if view.promotions[r].id == promo_id:
            return r
    raise AssertionError("promotion row not found")


class TestLiveStatusComputation:
    def test_active_promotion_within_its_window_shows_active(self, db_session):
        view = PromotionView()
        promo = _create(view)
        view.load_promotions()

        row = _row_for(view, promo.id)
        assert view.table.item(row, 5).text() == _t("common.active")

    def test_expired_promotion_shows_expired_not_active(self, db_session):
        view = PromotionView()
        now = datetime.now()
        promo = _create(view, start=now - timedelta(days=30), end=now - timedelta(days=1))
        view.load_promotions()

        row = _row_for(view, promo.id)
        assert view.table.item(row, 5).text() == _t("promotion.status_expired")

    def test_future_promotion_shows_upcoming_not_active(self, db_session):
        view = PromotionView()
        now = datetime.now()
        promo = _create(view, start=now + timedelta(days=1), end=now + timedelta(days=7))
        view.load_promotions()

        row = _row_for(view, promo.id)
        assert view.table.item(row, 5).text() == _t("promotion.status_upcoming")

    def test_manually_deactivated_promotion_shows_inactive_even_within_its_window(self, db_session):
        view = PromotionView()
        promo = _create(view, is_active=False)
        view.load_promotions()

        row = _row_for(view, promo.id)
        assert view.table.item(row, 5).text() == _t("common.inactive")


class TestEditPromotion:
    def test_double_click_opens_the_dialog_prefilled_and_saves_changes(self, db_session):
        view = PromotionView()
        promo = _create(view, name=f"Old_{_next_suffix()}")
        view.load_promotions()
        row = _row_for(view, promo.id)

        new_name = f"New_{_next_suffix()}"
        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 1
        fake_dialog.get_data.return_value = {
            "name": new_name,
            "type": "PERCENTAGE",
            "value": Decimal("10.00"),
            "start_time": promo.start_time,
            "end_time": promo.end_time,
            "days_of_week": None,
        }

        with patch.object(promotion_view_module, "PromotionDialog", return_value=fake_dialog) as mock_cls:
            view._edit_promotion_row(row)

        mock_cls.assert_called_once()
        _, kwargs = mock_cls.call_args
        assert kwargs["promotion"].id == promo.id
        updated = next(p for p in view.promotion_service.get_all_promotions() if p.id == promo.id)
        assert updated.name == new_name

    def test_declining_the_dialog_leaves_the_promotion_unchanged(self, db_session):
        view = PromotionView()
        promo = _create(view)
        view.load_promotions()
        row = _row_for(view, promo.id)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 0

        with patch.object(promotion_view_module, "PromotionDialog", return_value=fake_dialog):
            view._edit_promotion_row(row)

        fake_dialog.get_data.assert_not_called()
        updated = next(p for p in view.promotion_service.get_all_promotions() if p.id == promo.id)
        assert updated.name == promo.name


class TestToggleActive:
    def test_toggling_an_active_promotion_deactivates_it(self, db_session):
        view = PromotionView()
        promo = _create(view, is_active=True)
        view.load_promotions()
        row = _row_for(view, promo.id)

        view._toggle_promotion_active(row)

        updated = next(p for p in view.promotion_service.get_all_promotions() if p.id == promo.id)
        assert updated.is_active is False

    def test_toggling_an_inactive_promotion_reactivates_it(self, db_session):
        view = PromotionView()
        promo = _create(view, is_active=False)
        view.load_promotions()
        row = _row_for(view, promo.id)

        view._toggle_promotion_active(row)

        updated = next(p for p in view.promotion_service.get_all_promotions() if p.id == promo.id)
        assert updated.is_active is True


class TestDeletePromotion:
    def test_confirmed_delete_removes_the_promotion(self, db_session):
        view = PromotionView()
        promo = _create(view)
        view.load_promotions()
        row = _row_for(view, promo.id)

        with patch.object(promotion_view_module, "QMessageBox") as mock_box:
            mock_box.StandardButton.Yes = 1
            mock_box.StandardButton.No = 0
            mock_box.question.return_value = 1
            view._delete_promotion_row(row)

        remaining = [p.id for p in view.promotion_service.get_all_promotions()]
        assert promo.id not in remaining

    def test_declining_confirmation_keeps_the_promotion(self, db_session):
        view = PromotionView()
        promo = _create(view)
        view.load_promotions()
        row = _row_for(view, promo.id)

        with patch.object(promotion_view_module, "QMessageBox") as mock_box:
            mock_box.StandardButton.Yes = 1
            mock_box.StandardButton.No = 0
            mock_box.question.return_value = 0
            view._delete_promotion_row(row)

        remaining = [p.id for p in view.promotion_service.get_all_promotions()]
        assert promo.id in remaining


class TestPromotionDialogEditMode:
    def test_prefills_fields_from_an_existing_promotion(self, db_session):
        now = datetime.now()
        promo_view = PromotionView()
        promo = promo_view.promotion_service.create_promotion(
            name=f"Prefill_{_next_suffix()}",
            type="FIXED_AMOUNT",
            value=Decimal("25.00"),
            start_time=now,
            end_time=now + timedelta(days=3),
            days_of_week="0,1",
        )

        dialog = PromotionDialog(promotion=promo)

        assert dialog.name_input.text() == promo.name
        assert dialog.type_combo.currentText() == "FIXED_AMOUNT"
        assert dialog.value_input.value() == 25.00
        assert dialog.days_input.text() == "0,1"

    def test_new_dialog_has_empty_name(self, db_session):
        dialog = PromotionDialog()
        assert dialog.name_input.text() == ""

    def test_type_combo_includes_bogo(self, db_session):
        dialog = PromotionDialog()
        items = [dialog.type_combo.itemText(i) for i in range(dialog.type_combo.count())]
        assert "BOGO" in items

    def test_rejects_end_before_start_without_crashing(self, db_session):
        dialog = PromotionDialog()
        from PyQt6.QtCore import QDateTime

        dialog.start_dt.setDateTime(QDateTime.currentDateTime().addDays(5))
        dialog.end_dt.setDateTime(QDateTime.currentDateTime())
        dialog.name_input.setText("Whatever")

        with patch.object(promotion_view_module, "QMessageBox") as mock_box:
            dialog.validate_and_accept()

        mock_box.warning.assert_called_once()
