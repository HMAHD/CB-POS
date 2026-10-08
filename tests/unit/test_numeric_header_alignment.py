"""#554: numeric column headers right-align so they sit over their digits.

Headers were centered (Qt's default) above right-aligned numbers, so on
Documents, Stock Take, Price Lists and the Admin Tools DB tab every
amount column looked misaligned with its own header.
"""

from decimal import Decimal

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget

# Imported at module level so their ORM models are registered before the
# session-scoped test engine creates the tables.
from cbpos.core.models import Product
from cbpos.ui.views.admin_tools_view import AdminToolsView
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.stock_take_view import StockCountItemModel, StockTakeView
from cbpos.ui.widgets.table_helpers import align_numeric_headers

pytestmark = pytest.mark.usefixtures("qapp")


def _is_right(alignment) -> bool:
    return bool(Qt.AlignmentFlag(alignment) & Qt.AlignmentFlag.AlignRight)


def _right_header_columns(table: QTableWidget) -> set[int]:
    return {
        col
        for col in range(table.columnCount())
        if table.horizontalHeaderItem(col) is not None and _is_right(table.horizontalHeaderItem(col).textAlignment())
    }


class TestAlignNumericHeaders:
    def test_creates_missing_header_items(self, qtbot):
        table = QTableWidget(0, 3)
        qtbot.addWidget(table)

        align_numeric_headers(table, (2,))

        assert _right_header_columns(table) == {2}

    def test_alignment_survives_relabel(self, qtbot):
        table = QTableWidget(0, 3)
        qtbot.addWidget(table)
        table.setHorizontalHeaderLabels(["a", "b", "c"])
        align_numeric_headers(table, (1, 2))

        table.setHorizontalHeaderLabels(["x", "y", "z"])

        assert _right_header_columns(table) == {1, 2}
        assert table.horizontalHeaderItem(1).text() == "y"


class TestDocumentBrowser:
    def test_total_and_line_amount_headers_right_align(self, qtbot, db_session):
        view = DocumentBrowserView()
        qtbot.addWidget(view)

        assert _right_header_columns(view.doc_table) == {4}  # Total
        assert _right_header_columns(view.items_table) == {1, 2, 3, 4}  # Qty, Unit Price, Discount, Total

        view.retranslate_ui()
        assert _right_header_columns(view.doc_table) == {4}


class TestStockTake:
    def test_item_model_headers_match_cell_alignment(self):
        model = StockCountItemModel()
        for col in range(model.columnCount()):
            header = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.TextAlignmentRole)
            assert (header is not None and _is_right(header)) == (col >= 2)

    def test_history_items_and_variance_headers_right_align(self, qtbot, db_session):
        view = StockTakeView()
        qtbot.addWidget(view)

        assert _right_header_columns(view.history_table) == {3, 4}


class TestPriceLists:
    def test_price_headers_right_align(self, qtbot, db_session):
        view = PriceListView()
        qtbot.addWidget(view)

        assert _right_header_columns(view.table) == {2, 3}  # Base Price, List Price

    def test_price_cells_right_align_under_their_headers(self, qtbot, db_session):
        overridden = Product(barcode="HDR-ALIGN-1", name_en="Tea", price=Decimal("100.00"), cost=Decimal("50.00"))
        plain = Product(barcode="HDR-ALIGN-2", name_en="Milk", price=Decimal("80.00"), cost=Decimal("40.00"))
        db_session.add_all([overridden, plain])
        db_session.flush()
        view = PriceListView()
        qtbot.addWidget(view)
        price_list = view.price_list_service.create_price_list("Header Align List")
        view.price_list_service.set_item_price(price_list.id, overridden.id, Decimal("90.00"))
        view.current_list = price_list
        view.load_items()

        assert view.table.rowCount() >= 2
        for row in range(view.table.rowCount()):
            for col in (2, 3):  # "-" for no override aligns too
                assert _is_right(view.table.item(row, col).textAlignment())


class TestAdminToolsDatabaseTab:
    def test_rows_header_right_aligns(self, qtbot, db_session):
        view = AdminToolsView()
        qtbot.addWidget(view)

        assert _right_header_columns(view.table_counts) == {1}
