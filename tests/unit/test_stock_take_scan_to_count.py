"""
UI-053 (#547) / UI-047 (#615): StockTakeView had no
process_barcode_external, so scanning on Stock Take did nothing, and
adding a product already in the count showed an error popup instead of
counting it again.

A scan (or Enter in the add field) now adds the product if needed and
counts 1, jumping to its row; a repeat counts up. Weighed items get their
Counted editor opened instead, since +1 means nothing for kg.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QAbstractItemDelegate, QAbstractItemView, QMessageBox

from cbpos.core.models import Product, StockCountItem, Unit, User
from cbpos.core.services.stock_count_service import StockCountService
from cbpos.ui.views.stock_take_view import StockCountItemModel, StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")

COUNTED = StockCountItemModel.COL_COUNTED
SOAP, TEA, DHAL = "4790000000011", "4790000000028", "4790000000035"


@pytest.fixture
def fresh_reads(db_session, monkeypatch):
    """Give get_stock_count a clean identity map, like production's session-per-call.

    The test fixture shares one Session across every service call, so a
    StockCount created earlier stays identity-mapped and session.get()
    ignores the joinedload of its items.
    """
    original = StockCountService.get_stock_count

    def _get(stock_count_id):
        db_session.expunge_all()
        return original(stock_count_id)

    monkeypatch.setattr(StockCountService, "get_stock_count", staticmethod(_get))


@pytest.fixture
def warnings(monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, text, *a, **k: shown.append(text))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    return shown


@pytest.fixture
def view(db_session, fresh_reads, warnings):
    """A shown StockTakeView with a logged-in user and no count started yet."""
    kg = Unit(name="Kilogram (scan test)", abbreviation="kg", decimal_places=3)
    user = User(username="stk_scan_user", pin_hash="hash")
    dhal = Product(barcode=DHAL, name_en="Dhal", price=Decimal("300"), stock_qty=Decimal("2.5"), is_weighted=True)
    dhal.unit = kg
    db_session.add_all(
        [
            kg,
            user,
            Product(barcode=SOAP, name_en="Soap", price=Decimal("50"), stock_qty=Decimal("4")),
            Product(barcode=TEA, name_en="Tea", price=Decimal("90"), stock_qty=Decimal("6")),
            dhal,
        ]
    )
    db_session.flush()

    widget = StockTakeView()
    widget.set_user(SimpleNamespace(id=user.id))
    widget.show()
    yield widget
    if widget.item_table.state() == QAbstractItemView.State.EditingState:
        editor = widget.item_table.indexWidget(widget.item_table.currentIndex())
        if editor is not None:
            widget.counted_delegate.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
    widget.hide()


def _row_of(view, barcode):
    return next(r for r, i in enumerate(view.item_model.items) if i.product.barcode == barcode)


def _counted(db_session, view, barcode):
    return db_session.get(StockCountItem, view.item_model.items[_row_of(view, barcode)].id).counted_qty


class TestReAddCountsUp:
    def test_adding_a_product_already_in_the_count_increments_without_a_popup(self, view, db_session, warnings):
        view.search_input.setText(SOAP)
        view.add_single_product()
        view.search_input.setText(SOAP)
        view.add_single_product()

        assert warnings == []
        assert view.item_model.rowCount() == 1
        assert _counted(db_session, view, SOAP) == Decimal("2.000")
        assert view.search_input.text() == ""
