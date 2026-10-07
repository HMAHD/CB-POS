"""
UI-047 (#615) / UI-053 (#547): counting hundreds of items by keyboard was
slow -- a row click landed on the Product column (typing did nothing),
Enter didn't move on, and the Counted editor took any text, so a scan
landing in it could be saved as a 13-digit quantity.

Counted now: is the current column on any row change, edits on a click
of the selected cell, accepts only numbers with the unit's decimals
(max 6 integer digits), and Enter commits then opens the next row's
Counted cell.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QValidator
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemDelegate, QAbstractItemView, QMessageBox

from cbpos.core.models import Product, StockCountItem, Unit, User
from cbpos.core.services.stock_count_service import StockCountService
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.scanner import BarcodeScanner
from cbpos.ui.views.stock_take_view import StockCountItemModel, StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")

COUNTED = StockCountItemModel.COL_COUNTED


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
def view(db_session, monkeypatch, fresh_reads):
    """A shown StockTakeView with a draft count of: piece item, piece item, kg item."""
    for name in ("information", "warning"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)

    kg = Unit(name="Kilogram (editor test)", abbreviation="kg", decimal_places=3)
    user = User(username="stk_editor_user", pin_hash="hash")
    products = [
        Product(barcode="4790000000011", name_en="Soap", price=Decimal("50"), stock_qty=Decimal("4")),
        Product(barcode="4790000000028", name_en="Tea", price=Decimal("90"), stock_qty=Decimal("6")),
        Product(
            barcode="4790000000035", name_en="Dhal", price=Decimal("300"), stock_qty=Decimal("2.5"), is_weighted=True
        ),
    ]
    products[2].unit = kg
    db_session.add_all([kg, user, *products])
    db_session.flush()
    user_id = user.id
    stock_count = StockCountService.create_stock_count(user_id=user_id)
    for product in products:
        StockCountService.add_single_item(stock_count.id, product.id)

    widget = StockTakeView()
    widget.set_user(SimpleNamespace(id=user_id))
    widget.current_stock_count = stock_count
    widget._reload_items()
    widget.show()
    yield widget
    if widget.item_table.state() == QAbstractItemView.State.EditingState:
        editor = widget.item_table.indexWidget(widget.item_table.currentIndex())
        if editor is not None:
            widget.item_table.itemDelegateForColumn(COUNTED).closeEditor.emit(
                editor, QAbstractItemDelegate.EndEditHint.NoHint
            )
    widget.hide()


def _open_editor(view, row):
    index = view.item_model.index(row, COUNTED)
    view.item_table.setCurrentIndex(index)
    view.item_table.edit(index)
    editor = view.item_table.indexWidget(index)
    assert editor is not None
    return editor


def _counted(db_session, view, row):
    return db_session.get(StockCountItem, view.item_model.items[row].id).counted_qty


class TestCurrentColumnIsCounted:
    def test_selecting_another_column_moves_current_to_counted(self, view):
        view.item_table.setCurrentIndex(view.item_model.index(1, 1))

        assert view.item_table.currentIndex().row() == 1
        assert view.item_table.currentIndex().column() == COUNTED

    def test_selected_click_is_an_edit_trigger(self, view):
        assert view.item_table.editTriggers() & QAbstractItemView.EditTrigger.SelectedClicked


class TestCountedValidator:
    def test_piece_item_accepts_whole_numbers_only(self, view):
        validator = _open_editor(view, 0).validator()

        assert validator.validate("12", 0)[0] == QValidator.State.Acceptable
        assert validator.validate("1.5", 0)[0] == QValidator.State.Invalid
        assert validator.validate("abc", 0)[0] == QValidator.State.Invalid

    def test_weighed_item_accepts_the_units_decimals(self, view):
        validator = _open_editor(view, 2).validator()

        assert validator.validate("1.250", 0)[0] == QValidator.State.Acceptable
        assert validator.validate("1.2505", 0)[0] == QValidator.State.Invalid

    def test_barcode_length_number_is_rejected(self, view):
        validator = _open_editor(view, 0).validator()

        assert validator.validate("4796001550018", 0)[0] == QValidator.State.Invalid

    def test_model_refuses_an_absurd_quantity(self, view, db_session):
        assert not view.item_model.setData(view.item_model.index(0, COUNTED), "4796001550018")
        assert _counted(db_session, view, 0) is None

    def test_editor_opts_out_of_keeping_scans(self, view):
        editor = _open_editor(view, 0)

        assert editor.property(BarcodeScanner.SCAN_PASSTHROUGH_PROPERTY)


class TestEnterCommitsAndMovesDown:
    def test_enter_saves_and_opens_the_next_rows_counted_cell(self, view, db_session):
        editor = _open_editor(view, 0)
        editor.setText("7")

        QTest.keyClick(editor, Qt.Key.Key_Return)

        assert _counted(db_session, view, 0) == Decimal("7.000")
        assert view.item_table.currentIndex().row() == 1
        assert view.item_table.currentIndex().column() == COUNTED
        assert view.item_table.state() == QAbstractItemView.State.EditingState

    def test_enter_on_the_last_row_saves_and_stops_editing(self, view, db_session):
        editor = _open_editor(view, 2)
        editor.setText("1.25")

        QTest.keyClick(editor, Qt.Key.Key_Enter)

        assert _counted(db_session, view, 2) == Decimal("1.250")
        assert view.item_table.state() != QAbstractItemView.State.EditingState

    def test_saving_a_count_updates_the_progress_and_finalize_button(self, view):
        editor = _open_editor(view, 0)
        for _ in range(3):  # Enter opens the next row's editor itself
            editor.setText("1")
            QTest.keyClick(editor, Qt.Key.Key_Return)
            editor = view.item_table.indexWidget(view.item_table.currentIndex())

        assert view.lbl_counted.text() == _t("stock_take.counted_progress", counted=3, total=3)
        assert view.btn_finalize.isEnabled()
