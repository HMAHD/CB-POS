"""#558: Document Browser, Promotions, Stock Take, Credit Book and Admin Tools
format numbers with the shared helpers and right-align them.

They used ``:.2f``/``str()``: no separators, left-aligned values, a raw
"PERCENT 10" discount, an ambiguous promotion "10.00" (10% or Rs. 10?),
and every stock count as "12.000" regardless of the unit.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt

from cbpos.core.models import Promotion
from cbpos.core.utils.formatters import NO_VALUE, format_currency, get_currency_symbol
from cbpos.ui.views.stock_take_view import StockCountItemModel

pytestmark = pytest.mark.usefixtures("qapp")

RIGHT = Qt.AlignmentFlag.AlignRight


def _right(alignment) -> bool:
    return bool(Qt.AlignmentFlag(int(alignment)) & RIGHT) if alignment is not None else False


def _header_right(table, col) -> bool:
    return _right(table.horizontalHeaderItem(col).textAlignment())


# --- Stock Take -------------------------------------------------------------


def _count_item(expected, counted, unit_places, weighted=False):
    product = SimpleNamespace(
        barcode="B1", name_en="P", unit=SimpleNamespace(decimal_places=unit_places), is_weighted=weighted
    )
    return SimpleNamespace(
        product=product,
        expected_qty=Decimal(expected),
        counted_qty=Decimal(counted),
        variance_qty=Decimal(counted) - Decimal(expected),
        variance_value=Decimal("0"),
    )


def test_stock_take_piece_shows_whole_numbers_and_kg_three_decimals():
    model = StockCountItemModel([_count_item("12.000", "1250.000", 0), _count_item("1.250", "1.250", 3, True)])
    display = Qt.ItemDataRole.DisplayRole
    assert model.data(model.index(0, 2), display) == "12"
    assert model.data(model.index(0, 3), display) == "1,250"
    assert model.data(model.index(1, 2), display) == "1.250"
    assert model.data(model.index(1, 3), display) == "1.250"
    for col in (2, 3, 4, 5):
        assert _right(model.data(model.index(0, col), Qt.ItemDataRole.TextAlignmentRole))


# --- Promotions ---------------------------------------------------------------


def test_promotions_value_column_shows_percent_amount_or_dash(db_session):
    from cbpos.ui.views.promotion_view import PromotionView

    now = datetime.now()
    common = {"start_time": now - timedelta(days=1), "end_time": now + timedelta(days=1)}
    promos = [
        Promotion(name="Pct", type="PERCENTAGE", value=Decimal("10.00"), **common),
        Promotion(name="Fixed", type="FIXED_AMOUNT", value=Decimal("10.00"), **common),
        Promotion(name="Big", type="FIXED_AMOUNT", value=Decimal("1500.00"), **common),
        Promotion(name="Bogo", type="BOGO", value=Decimal("0"), **common),
    ]
    db_session.add_all(promos)
    db_session.flush()

    view = PromotionView()
    values = {view.promotions[r].name: view.table.item(r, 2) for r in range(view.table.rowCount())}
    symbol = get_currency_symbol()
    assert values["Pct"].text() == "10%"
    assert values["Fixed"].text() == f"{symbol} 10.00"
    assert values["Big"].text() == f"{symbol} 1,500.00"
    assert values["Bogo"].text() == NO_VALUE
    assert all(_right(item.textAlignment()) for item in values.values())
    assert _header_right(view.table, 2)
    view.deleteLater()


# --- Document Browser ---------------------------------------------------------


def test_document_browser_discount_is_readable_and_right_aligned(db_session):
    from cbpos.ui.views.document_view import DocumentBrowserView

    view = DocumentBrowserView()
    line = {"quantity": Decimal("1"), "unit_price": Decimal("100"), "line_total": Decimal("90")}
    doc = {
        "type": "sale",
        "document_number": "S-1",
        "date": datetime.now(),
        "status": "COMPLETED",
        "items": [
            {**line, "product_name": "A", "discount_type": "PERCENTAGE", "discount_value": Decimal("10.00")},
            {**line, "product_name": "B", "discount_type": "FIXED", "discount_value": Decimal("50.00")},
            {**line, "product_name": "C", "discount_type": "NONE", "discount_value": Decimal("0")},
        ],
    }
    view.display_details(doc)
    discount = [view.items_table.item(r, 3) for r in range(3)]
    assert [d.text() for d in discount] == ["10%", format_currency(Decimal("50")), ""]
    assert all(_right(d.textAlignment()) for d in discount)
    assert _header_right(view.items_table, 3)
    view.deleteLater()


# --- Credit Book --------------------------------------------------------------


def test_credit_book_amounts_have_separators_and_symbol_in_header(db_session):
    from cbpos.ui.views.credit_book_view import CreditBookView

    view = CreditBookView()
    customer = SimpleNamespace(
        id=1,
        name="C",
        phone="",
        current_debt=Decimal("12345.5"),
        credit_limit=Decimal("50000"),
        loyalty_points=1234,
    )
    view.populate_customer_table([customer])
    assert view.customer_table.item(0, 3).text() == "12,345.50"
    assert view.customer_table.item(0, 4).text() == "50,000.00"
    assert view.customer_table.item(0, 5).text() == "1,234"
    for col in (3, 4, 5):
        assert _right(view.customer_table.item(0, col).textAlignment())
        assert _header_right(view.customer_table, col)
    assert view.customer_table.horizontalHeaderItem(3).text().endswith(f"({get_currency_symbol()})")

    entry = SimpleNamespace(
        timestamp=datetime.now(),
        entry_type="SALE",
        reference_doc="S-1",
        note=None,
        amount=Decimal("2500"),
        balance_after=Decimal("12345.5"),
    )
    view.populate_ledger([entry])
    assert view.ledger_table.item(0, 3).text() == "2,500.00"
    assert view.ledger_table.item(0, 5).text() == "12,345.50"
    for col in (3, 4, 5):
        assert _header_right(view.ledger_table, col)
    view.deleteLater()


# --- Admin Tools --------------------------------------------------------------


def test_admin_tools_row_counts_have_separators(db_session):
    from cbpos.ui.views import admin_tools_view
    from cbpos.ui.views.admin_tools_view import AdminToolsView

    view = AdminToolsView()
    info = {"tables": [{"name": "sales", "rows": 1234567}, {"name": "users", "rows": 3}]}
    with patch.object(admin_tools_view.MaintenanceService, "get_full_database_info", return_value=info):
        view._load_db_info()
    assert view.table_counts.item(0, 1).text() == "1,234,567"
    assert view.table_counts.item(1, 1).text() == "3"
    assert _right(view.table_counts.item(0, 1).textAlignment())
    view.deleteLater()
