"""Unit tests for guiding empty states across empty tables (#596 [UI-029]).

Verifies:
1. EmptyStateWidget auto-resizing with parent viewport and QLabel compatibility methods.
2. Suppliers and GRN empty state overlays in PurchaseView.
3. Items empty state overlay and history placeholder row in StockTakeView.
4. Contextual empty state in CreditBookView (date range vs no transaction history).
5. All empty state strings translate in EN, SI, and TA.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QApplication, QWidget

from cbpos.i18n import _t, set_language
from cbpos.ui.resources.icons import Icons
from cbpos.ui.views.credit_book_view import CreditBookView
from cbpos.ui.views.purchase_view import PurchaseView
from cbpos.ui.views.stock_take_view import StockCountItemModel, StockTakeView
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestEmptyStateWidgetBasics:
    def test_auto_resizes_with_parent_viewport(self):
        parent = QWidget()
        parent.resize(400, 300)
        widget = EmptyStateWidget(Icons.SALES, parent)
        widget.show()

        assert widget.size() == QSize(400, 300)

        QApplication.sendEvent(parent, QResizeEvent(QSize(600, 450), QSize(400, 300)))
        assert widget.size() == QSize(600, 450)

    def test_text_and_set_text_compatibility(self):
        widget = EmptyStateWidget(Icons.SALES)
        widget.setText("Test Title")
        assert widget.text() == "Test Title"
        assert widget._title_label.text() == "Test Title"


class TestPurchaseViewEmptyStates:
    def test_supplier_and_grn_empty_state_widgets_exist(self, qtbot, db_session):
        view = PurchaseView()
        qtbot.addWidget(view)

        assert isinstance(view.empty_supplier_label, EmptyStateWidget)
        assert isinstance(view.empty_grn_label, EmptyStateWidget)
        assert isinstance(view.empty_history_label, EmptyStateWidget)

    def test_grn_empty_state_toggles_with_items(self, qtbot, db_session):
        view = PurchaseView()
        qtbot.addWidget(view)

        assert not view.empty_grn_label.isHidden()

        # Simulate adding an item to GRN
        view._add_grn_row(
            product=MagicMock(id=1, name_en="Test Product", cost=Decimal("10.00")),
            qty=Decimal("2"),
            cost=Decimal("10.00"),
        )
        assert view.empty_grn_label.isHidden()

        # Remove item
        view.grn_model.setRowCount(0)
        assert not view.empty_grn_label.isHidden()


class TestStockTakeViewEmptyStates:
    def test_stock_take_items_empty_state_exists_and_toggles(self, qtbot, db_session):
        view = StockTakeView()
        qtbot.addWidget(view)

        assert isinstance(view.empty_items_label, EmptyStateWidget)
        assert not view.empty_items_label.isHidden()

        # Set model with items
        mock_item = MagicMock(
            barcode="123456",
            product_name="Sample",
            expected_qty=Decimal("5"),
            counted_qty=None,
            variance=None,
            variance_value=None,
        )
        model = StockCountItemModel([mock_item])
        view._set_item_model(model)
        assert view.empty_items_label.isHidden()

        # Clear model
        view._set_item_model(StockCountItemModel([]))
        assert not view.empty_items_label.isHidden()

    def test_stock_take_history_shows_placeholder_when_empty(self, qtbot, db_session, monkeypatch):
        from cbpos.core.services.stock_count_service import StockCountService

        monkeypatch.setattr(StockCountService, "get_all_stock_counts", lambda **kwargs: [])
        view = StockTakeView()
        qtbot.addWidget(view)

        view.refresh_history()
        assert view.history_table.rowCount() == 1
        item = view.history_table.item(0, 0)
        assert item.text() == _t("stock_take.no_history_found")
        assert view.history_table.columnSpan(0, 0) == view.history_table.columnCount()


class TestCreditBookLedgerEmptyStates:
    def test_shows_no_history_when_customer_has_zero_transactions(self, qtbot, db_session, monkeypatch):
        from cbpos.core.services.customer_credit_service import CustomerCreditService

        monkeypatch.setattr(CustomerCreditService, "get_ledger", lambda *args, **kwargs: [])
        view = CreditBookView()
        qtbot.addWidget(view)

        view.selected_customer = MagicMock(id=1)
        view.populate_ledger([])

        assert view.ledger_table.rowCount() == 1
        item = view.ledger_table.item(0, 0)
        assert item.text() == _t("credit_book.ledger_no_history")
        assert view.ledger_table.columnSpan(0, 0) == view.ledger_table.columnCount()

    def test_shows_empty_range_when_entries_filtered_by_date(self, qtbot, db_session, monkeypatch):
        from cbpos.core.services.customer_credit_service import CustomerCreditService

        # Return entries when called without dates, but empty when called with dates
        def mock_get_ledger(customer_id, date_from=None, date_to=None):
            if date_from or date_to:
                return []
            return [MagicMock(amount=Decimal("10.00"), balance_after=Decimal("10.00"))]

        monkeypatch.setattr(CustomerCreditService, "get_ledger", mock_get_ledger)
        view = CreditBookView()
        qtbot.addWidget(view)

        view.selected_customer = MagicMock(id=1)
        view.reload_ledger()

        assert view.ledger_table.rowCount() == 1
        item = view.ledger_table.item(0, 0)
        assert item.text() == _t("credit_book.ledger_empty_range")


class TestEmptyStateTranslations:
    EMPTY_KEYS = [
        "purchase.empty_suppliers_title",
        "purchase.empty_suppliers_subtitle",
        "purchase.empty_grn_items_title",
        "purchase.empty_grn_items_subtitle",
        "purchase.empty_history_subtitle",
        "stock_take.empty_items_title",
        "stock_take.empty_items_subtitle",
        "stock_take.no_history_found",
        "credit_book.ledger_empty_range",
        "credit_book.ledger_no_history",
    ]

    @pytest.mark.parametrize("lang", ["en", "si", "ta"])
    def test_keys_exist_in_all_languages(self, lang):
        set_language(lang)
        for key in self.EMPTY_KEYS:
            val = _t(key)
            assert val != key, f"Missing key '{key}' in language '{lang}'"
            assert len(val.strip()) > 0
        set_language("en")
