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
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemDelegate, QAbstractItemView, QApplication, QMessageBox

from cbpos.core.models import Product, StockCountItem, Unit, User
from cbpos.core.services.stock_count_service import StockCountService
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.scanner import BarcodeScanner
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
    widget.set_user(SimpleNamespace(id=user.id, role=SimpleNamespace(name="Admin", permissions=[])))
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


class TestScanCounts:
    def test_first_scan_starts_a_count_adds_the_item_and_counts_one(self, view, db_session):
        view.process_barcode_external(SOAP)

        assert view.current_stock_count is not None
        assert _counted(db_session, view, SOAP) == Decimal("1.000")
        current = view.item_table.currentIndex()
        assert (current.row(), current.column()) == (_row_of(view, SOAP), COUNTED)

    def test_repeat_scan_counts_up(self, view, db_session):
        view.process_barcode_external(SOAP)
        view.process_barcode_external(TEA)
        view.process_barcode_external(SOAP)

        assert _counted(db_session, view, SOAP) == Decimal("2.000")
        assert _counted(db_session, view, TEA) == Decimal("1.000")
        assert view.item_table.currentIndex().row() == _row_of(view, SOAP)

    def test_scan_from_history_tab_switches_to_new_count(self, view):
        view.tabs.setCurrentIndex(1)

        view.process_barcode_external(SOAP)

        assert view.tabs.currentIndex() == 0

    def test_unknown_barcode_warns_and_adds_nothing(self, view, warnings):
        view.process_barcode_external("0000000000000")

        assert len(warnings) == 1
        assert view.item_model.rowCount() == 0


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


class TestWeighedItems:
    def test_scan_opens_the_counted_editor_instead_of_adding_one(self, view, db_session):
        view.process_barcode_external(DHAL)

        assert _counted(db_session, view, DHAL) is None
        assert view.item_table.currentIndex().row() == _row_of(view, DHAL)
        assert view.item_table.state() == QAbstractItemView.State.EditingState


class TestScanWhileEditing:
    def test_scan_into_an_open_counted_editor_is_not_saved_as_a_quantity(self, view, db_session):
        view.process_barcode_external(SOAP)
        view.process_barcode_external(TEA)
        index = view.item_model.index(_row_of(view, SOAP), COUNTED)
        view.item_table.setCurrentIndex(index)
        view.item_table.edit(index)
        editor = view.item_table.indexWidget(index)

        app = QApplication.instance()
        scanner = BarcodeScanner(app)
        scanner.barcode_scanned.connect(view.process_barcode_external)
        try:
            QTest.keyClicks(editor, TEA)
            QTest.keyClick(editor, Qt.Key.Key_Return)
        finally:
            app.removeEventFilter(scanner)

        assert _counted(db_session, view, SOAP) == Decimal("1.000")
        assert _counted(db_session, view, TEA) == Decimal("2.000")


GHEE, DELIVERY = "4790000000042", "4790000000059"


@pytest.fixture
def more_products(db_session):
    """A loose-sold item (kg unit, not flagged weighed) and a service."""
    kg = Unit(name="Kilogram (scan test 2)", abbreviation="kg", decimal_places=3)
    ghee = Product(barcode=GHEE, name_en="Loose Ghee", price=Decimal("900"), stock_qty=Decimal("1.5"))
    ghee.unit = kg
    delivery = Product(barcode=DELIVERY, name_en="Delivery", price=Decimal("200"), is_service=True)
    db_session.add_all([kg, ghee, delivery])
    db_session.flush()


class TestScanAcceptance:
    """#548 QA: scanning an item twice shows Counted = 2 and selects its row."""

    def test_two_scans_show_counted_two_and_select_the_row(self, view, db_session):
        view.process_barcode_external(TEA)
        view.process_barcode_external(SOAP)
        view.process_barcode_external(SOAP)

        row = _row_of(view, SOAP)
        assert view.item_model.index(row, COUNTED).data() == "2"
        assert [i.row() for i in view.item_table.selectionModel().selectedRows()] == [row]

    def test_scan_shows_brief_feedback_naming_the_product(self, view):
        view.process_barcode_external(SOAP)
        view.process_barcode_external(SOAP)

        assert view.lbl_scan_feedback.isVisible()
        assert view.lbl_scan_feedback.text() == _t("stock_take.scan_counted", product="Soap", counted="2")

        view._scan_feedback_timer.timeout.emit()

        assert not view.lbl_scan_feedback.isVisible()


class TestMeasuredUnits:
    def test_item_sold_by_a_fractional_unit_opens_the_editor(self, view, db_session, more_products):
        view.process_barcode_external(GHEE)

        assert _counted(db_session, view, GHEE) is None
        assert view.item_table.state() == QAbstractItemView.State.EditingState
        assert view.lbl_scan_feedback.text() == _t("stock_take.scan_enter_quantity", product="Loose Ghee")


class TestScope:
    def test_scanning_a_service_warns_and_adds_nothing(self, view, warnings, more_products):
        view.process_barcode_external(DELIVERY)

        assert warnings == [_t("stock_take.service_not_counted")]
        assert view.item_model.rowCount() == 0


class TestScanOnHistoryTable:
    def test_scan_with_the_history_table_focused_counts_instead_of_opening(self, view, db_session, monkeypatch):
        """History's Enter-to-open shortcut (#594) must not eat a scanner's Enter."""
        opened: list[int] = []
        monkeypatch.setattr(StockTakeView, "open_history_report", lambda _self, sc_id: opened.append(sc_id))
        view.process_barcode_external(SOAP)  # one count in History to select
        view.tabs.setCurrentWidget(view.history_tab)
        view.history_table.selectRow(0)
        view.activateWindow()
        QTest.qWaitForWindowActive(view)
        view.history_table.setFocus()

        app = QApplication.instance()
        scanner = BarcodeScanner(app)
        scanner.barcode_scanned.connect(view.process_barcode_external)
        try:
            QTest.keyClicks(view.history_table, SOAP)
            QTest.keyClick(view.history_table, Qt.Key.Key_Return)
        finally:
            app.removeEventFilter(scanner)

        assert opened == []
        assert view.tabs.currentWidget() is view.new_count_tab
        assert _counted(db_session, view, SOAP) == Decimal("2.000")
