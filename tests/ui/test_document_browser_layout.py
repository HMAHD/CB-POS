"""
#612 (UI-044): the Document Browser split list and detail panel 3:2
top-to-bottom, so at 1366x768 only 6-7 documents were visible; the line
items were capped at 200px and the summary was one <br>-joined label whose
values didn't line up. The detail panel now sits beside the list.
"""

import re
from datetime import datetime
from decimal import Decimal

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from cbpos.core.utils.formatters import format_currency
from cbpos.ui.views import document_view as document_view_module
from cbpos.ui.views.document_view import DocumentBrowserView

pytestmark = pytest.mark.usefixtures("qapp")

# Documents tab content area at 1366x768: maximised window minus the
# Windows taskbar and title bar, minus the 250px Management sidebar.
CONTENT_W, CONTENT_H = 1366 - 250, 768 - 40 - 30


def _doc(i: int) -> dict:
    return {
        "id": i,
        "type": "SALE",
        "document_number": f"REC-{i:05d}",
        "date": datetime(2026, 10, 1, 9, i % 60),
        "entity_name": f"Customer {i}",
        "total_amount": Decimal("1250.00") + i,
        "status": "COMPLETED",
        "username": "cashier",
    }


def _details(doc_id: int, doc_type: str) -> dict:
    return {
        "id": doc_id,
        "type": "sale",
        "document_number": f"REC-{doc_id:05d}",
        "date": datetime(2026, 10, 1, 9, 0),
        "status": "COMPLETED",
        "username": "cashier",
        "entity_name": f"Customer {doc_id}",
        "total_amount": Decimal("1250.00") + doc_id,
        "tax_vat": Decimal("190.68"),
        "tax_sscl": Decimal("15.63"),
        "net_revenue": Decimal("1043.69"),
        "items": [
            {
                "product_name": f"Item {n}",
                "quantity": Decimal("1"),
                "unit_price": Decimal("125.00"),
                "discount_type": None,
                "discount_value": None,
                "line_total": Decimal("125.00"),
            }
            for n in range(10)
        ],
        "payments": [{"method": "CASH", "amount": Decimal("1250.00") + doc_id}],
    }


@pytest.fixture
def view(db_session, monkeypatch):
    service = document_view_module.DocumentBrowserService
    monkeypatch.setattr(
        service, "search_documents", staticmethod(lambda **k: {"total": 40, "documents": [_doc(i) for i in range(40)]})
    )
    monkeypatch.setattr(service, "get_document_details", staticmethod(_details))
    v = DocumentBrowserView()
    v.resize(CONTENT_W, CONTENT_H)
    v.show()
    v.activateWindow()
    QTest.qWaitForWindowActive(v)
    yield v
    v.hide()
    v.deleteLater()


def _select(view: DocumentBrowserView, row: int) -> None:
    view.doc_table.selectRow(row)
    QApplication.processEvents()


def _in_view(view, widget):
    return widget.geometry().translated(widget.parentWidget().mapTo(view, QPoint(0, 0)))


class TestListKeepsTheHeight:
    def test_detail_panel_opens_beside_the_list_not_below_it(self, view):
        _select(view, 0)

        assert view.detail_panel.isVisible()
        table, panel = _in_view(view, view.doc_table), _in_view(view, view.detail_panel)
        assert panel.left() > table.right()
        assert panel.top() < table.bottom() and panel.bottom() > table.top()

    def test_at_least_12_rows_visible_at_1366x768_with_the_panel_open(self, view):
        _select(view, 0)

        visible_rows = view.doc_table.viewport().height() // view.doc_table.rowHeight(0)
        assert visible_rows >= 12

    def test_line_items_are_not_capped_at_200px(self, view):
        assert view.items_table.maximumHeight() > 200

    def test_discount_column_only_shows_when_a_line_has_a_discount(self, view, monkeypatch):
        _select(view, 0)
        assert view.items_table.isColumnHidden(3)

        def with_discount(doc_id, doc_type):
            details = _details(doc_id, doc_type)
            details["items"][0].update(discount_type="PERCENTAGE", discount_value=Decimal("10"))
            return details

        monkeypatch.setattr(document_view_module.DocumentBrowserService, "get_document_details", with_discount)
        _select(view, 1)
        assert not view.items_table.isColumnHidden(3)

    def test_user_column_steps_aside_while_the_panel_shows_it(self, view):
        """The panel repeats the user, so the list gives that width to the customer name."""
        _select(view, 0)
        assert view.doc_table.isColumnHidden(6)

        view.btn_close_detail.click()
        assert not view.doc_table.isColumnHidden(6)


class TestArrowKeysBrowse:
    def test_down_arrow_shows_the_next_documents_details(self, view):
        _select(view, 0)
        view.doc_table.setFocus()

        QTest.keyClick(view.doc_table, Qt.Key.Key_Down)

        assert view.current_doc["document_number"] == "REC-00001"
        assert "REC-00001" in view.detail_title.text()


class TestSummaryLinesUp:
    def test_summary_is_a_two_column_table(self, view):
        _select(view, 2)

        html = view.details_label.text()
        assert "<table" in html
        assert re.search(r"<tr>\s*<td[^>]*>[^<]*</td>\s*<td", html)

    def test_money_values_are_right_aligned(self, view):
        _select(view, 2)

        html = view.details_label.text()
        for amount in (Decimal("1252.00"), Decimal("190.68"), Decimal("15.63"), Decimal("1043.69")):
            cell = re.search(r'<td[^>]*align="right"[^>]*>(?:<b>)?' + re.escape(format_currency(amount)), html)
            assert cell, f"{format_currency(amount)} not in a right-aligned cell"


class TestHeaderBar:
    def test_title_and_close_share_a_header_bar(self, view):
        _select(view, 0)

        bar = view.btn_close_detail.parentWidget()
        assert bar.objectName() == "DocDetailHeader"
        assert view.detail_title.parentWidget() is bar

    def test_close_hides_the_panel_and_the_list_takes_the_width_back(self, view):
        _select(view, 0)
        narrow = view.doc_table.width()

        view.btn_close_detail.click()
        QApplication.processEvents()

        assert not view.detail_panel.isVisible()
        assert view.doc_table.width() > narrow
