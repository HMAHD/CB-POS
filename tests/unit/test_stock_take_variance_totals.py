"""
UI-069 (#644): the Stock Take stats bar summed the *absolute* variance while
the report, finalize and approve dialogs showed the stored total, all
labelled "Variance" -- +500 and -500 read Rs. 1,000 on one screen and Rs. 0
on another, so owners couldn't trust either.

Two figures now, computed in one place (StockCountService.variance_totals)
and shown with the same labels everywhere: "Net variance" (signed sum) and
"Total discrepancy" (sum of absolute values).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Product, User
from cbpos.core.services.stock_count_service import StockCountService, VarianceTotals
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.ui.views.stock_take_view import StockCountReportDialog, StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")

NET_ZERO = _t("stock_take.net_variance_amount", amount=format_currency(Decimal("0")))
DISCREPANCY_1000 = _t("stock_take.total_discrepancy_amount", amount=format_currency(Decimal("1000")))


def _item(value):
    return SimpleNamespace(variance_value=None if value is None else Decimal(value))


class TestVarianceTotals:
    def test_surplus_and_shortage_cancel_in_net_but_add_in_discrepancy(self):
        totals = StockCountService.variance_totals([_item("500"), _item("-500")])

        assert totals == VarianceTotals(net=Decimal("0.00"), discrepancy=Decimal("1000.00"))

    def test_uncounted_items_are_skipped(self):
        totals = StockCountService.variance_totals([_item("-120.50"), _item(None), _item("20")])

        assert totals.net == Decimal("-100.50")
        assert totals.discrepancy == Decimal("140.50")

    def test_no_items_is_zero(self):
        assert StockCountService.variance_totals([]) == VarianceTotals(Decimal("0.00"), Decimal("0.00"))


@pytest.fixture
def fresh_reads(db_session, monkeypatch):
    """Give get_stock_count a clean identity map, like production's session-per-call."""
    original = StockCountService.get_stock_count

    def _get(stock_count_id):
        db_session.expunge_all()
        return original(stock_count_id)

    monkeypatch.setattr(StockCountService, "get_stock_count", staticmethod(_get))


@pytest.fixture
def balanced_count(db_session, fresh_reads):
    """A DRAFT count with one Rs. 500 surplus and one Rs. 500 shortage, all counted."""
    user = User(username="stk_variance_totals_user", pin_hash="hash")
    over = Product(barcode="STK-VAR-OVER", name_en="Over", price=Decimal("150"), cost=Decimal("100"))
    over.stock_qty = Decimal("5")
    under = Product(barcode="STK-VAR-UNDER", name_en="Under", price=Decimal("150"), cost=Decimal("100"))
    under.stock_qty = Decimal("10")
    db_session.add_all([user, over, under])
    db_session.flush()
    user_id = user.id
    stock_count = StockCountService.create_stock_count(user_id=user_id)
    StockCountService.update_count(StockCountService.add_single_item(stock_count.id, over.id).id, Decimal("10"))
    StockCountService.update_count(StockCountService.add_single_item(stock_count.id, under.id).id, Decimal("5"))
    return stock_count.id, user_id


@pytest.fixture
def messages(monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, text, *a, **k: shown.append(text))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *a, **k: shown.append(text))

    def _question(_p, _t, text, *a, **k):
        shown.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", _question)
    return shown


@pytest.fixture
def view(balanced_count):
    stock_count_id, user_id = balanced_count
    widget = StockTakeView()
    widget.set_user(SimpleNamespace(id=user_id))
    widget.resume_draft_count(stock_count_id)
    yield widget
    widget.deleteLater()


class TestEveryScreenShowsBothFigures:
    def test_stats_bar(self, view):
        assert view.lbl_net_variance.text() == NET_ZERO
        assert view.lbl_discrepancy.text() == DISCREPANCY_1000
        assert view.lbl_net_variance.toolTip()
        assert view.lbl_discrepancy.toolTip()

    def test_finalize_dialog(self, view, messages):
        view.finalize_count()

        assert NET_ZERO in messages[-1]
        assert DISCREPANCY_1000 in messages[-1]
        # The stats bar still agrees after the reload
        assert view.lbl_net_variance.text() == NET_ZERO
        assert view.lbl_discrepancy.text() == DISCREPANCY_1000

    def test_approve_dialog(self, view, messages):
        view.finalize_count()
        messages.clear()

        view.approve_and_apply()

        confirm = messages[0]
        assert NET_ZERO in confirm
        assert DISCREPANCY_1000 in confirm

    def test_report_dialog(self, balanced_count):
        stock_count_id, _user_id = balanced_count
        StockCountService.finalize_count(stock_count_id)

        dialog = StockCountReportDialog(stock_count_id)
        try:
            assert dialog.lbl_net_variance_key.text() == _t("stock_take.net_variance")
            assert dialog.lbl_net_variance_val.text() == format_currency(Decimal("0"))
            assert dialog.lbl_discrepancy_key.text() == _t("stock_take.total_discrepancy")
            assert dialog.lbl_discrepancy_val.text() == format_currency(Decimal("1000"))
        finally:
            dialog.deleteLater()

    def test_history_row(self, view, balanced_count):
        view.tabs.setCurrentWidget(view.history_tab)
        headers = [view.history_table.horizontalHeaderItem(c).text() for c in range(view.history_table.columnCount())]

        net_col = headers.index(_t("stock_take.net_variance"))
        discrepancy_col = headers.index(_t("stock_take.total_discrepancy"))
        assert view.history_table.item(0, net_col).text() == format_currency(Decimal("0"))
        assert view.history_table.item(0, discrepancy_col).text() == format_currency(Decimal("1000"))


class TestStoredTotalIsTheDiscrepancy:
    def test_finalize_and_approve_store_the_discrepancy(self, balanced_count):
        stock_count_id, user_id = balanced_count

        assert StockCountService.finalize_count(stock_count_id).total_variance_value == Decimal("1000.00")
        completed = StockCountService.approve_and_apply(stock_count_id, user_id)

        assert completed.status == DocumentStatus.COMPLETED
        assert completed.total_variance_value == Decimal("1000.00")


class TestSignedColour:
    def test_shortage_net_is_painted_danger(self, db_session, fresh_reads):
        from cbpos.ui.resources.status_colors import DANGER, status_hex

        user = User(username="stk_variance_colour_user", pin_hash="hash")
        product = Product(barcode="STK-VAR-SHORT", name_en="Short", price=Decimal("10"), cost=Decimal("4"))
        product.stock_qty = Decimal("3")
        db_session.add_all([user, product])
        db_session.flush()
        stock_count = StockCountService.create_stock_count(user_id=user.id)
        StockCountService.update_count(StockCountService.add_single_item(stock_count.id, product.id).id, Decimal("1"))

        widget = StockTakeView()
        try:
            widget.resume_draft_count(stock_count.id)
            assert status_hex(DANGER).lower() in widget.lbl_net_variance.styleSheet().lower()
            assert widget.lbl_net_variance.text().startswith(_t("stock_take.net_variance"))
        finally:
            widget.deleteLater()
