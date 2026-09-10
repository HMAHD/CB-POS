"""
#311: Load Products, Finalize Count, and Refresh (History tab) all
rendered as the exact same green (class="primary"), and Approve & Apply
added a *fourth* shade of green via a hardcoded inline setStyleSheet(),
bypassing the class system entirely. Color stops meaning anything when
three semantically different actions (fetch data, complete a count,
apply to inventory) all look the same. Reserve one class per action
category: secondary/neutral for data-fetch (Load Products, Refresh, New
Count), primary for the two "make this count official" actions
(Finalize, Approve), routed through the class system so neither can
drift from the other independently again.
"""

import pytest

from cbpos.ui.views.stock_take_view import StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")


class TestDataFetchActionsAreNeutral:
    def test_load_products_is_secondary_not_primary(self, db_session):
        view = StockTakeView()
        assert view.btn_load.property("class") == "secondary"

    def test_refresh_history_is_secondary_not_primary(self, db_session):
        view = StockTakeView()
        assert view.hist_refresh_btn.property("class") == "secondary"

    def test_new_count_has_a_neutral_class(self, db_session):
        view = StockTakeView()
        assert view.btn_new.property("class") == "secondary"


class TestCommitActionsShareOneColor:
    def test_finalize_is_primary(self, db_session):
        view = StockTakeView()
        assert view.btn_finalize.property("class") == "primary"

    def test_approve_is_primary_not_a_hardcoded_style(self, db_session):
        view = StockTakeView()
        assert view.btn_approve.property("class") == "primary"
        assert view.btn_approve.styleSheet() == ""


class TestUnchangedButtons:
    def test_save_draft_stays_accent(self, db_session):
        view = StockTakeView()
        assert view.btn_save_draft.property("class") == "accent"

    def test_void_stays_danger(self, db_session):
        view = StockTakeView()
        assert view.btn_void.property("class") == "danger"
