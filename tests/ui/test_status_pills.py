"""#560: statuses are theme-aware pills; DRAFT and SUSPENDED differ; the
Payment Methods status pill sits next to the name, not among the buttons.
"""

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem, QTableWidget, QTableWidgetItem

from cbpos.core.models import PaymentMethod
from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.resources.status_colors import SUCCESS, pill_colors
from cbpos.ui.widgets.status_pill_delegate import STATUS_MEANING_ROLE, StatusPillDelegate, set_status_pill

pytestmark = pytest.mark.usefixtures("qapp")

STYLES = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


@pytest.fixture(params=["Dark", "Light"])
def theme(request, monkeypatch):
    monkeypatch.setattr(ThemeService, "current_theme", request.param)
    return request.param


def _paint_cell(selected: bool) -> tuple[QImage, QRect]:
    table = QTableWidget(1, 1)
    item = set_status_pill(QTableWidgetItem(), "COMPLETED", SUCCESS)
    table.setItem(0, 0, item)
    delegate = StatusPillDelegate(table)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 160, 32)
    option.widget = table
    option.font = table.font()
    if selected:
        option.state |= QStyle.StateFlag.State_Selected
    image = QImage(160, 32, QImage.Format.Format_ARGB32)
    image.fill(QColor("#007ACC"))
    painter = QPainter(image)
    delegate.paint(painter, option, table.model().index(0, 0))
    painter.end()
    table.deleteLater()
    return image, option.rect


@pytest.mark.parametrize("selected", [False, True])
def test_pill_keeps_its_own_fill_on_selected_rows(theme, selected):
    image, rect = _paint_cell(selected)
    _text, fill = pill_colors(SUCCESS)
    # Just inside the pill's left end, vertically centred: the pill fill, not the selection.
    assert image.pixelColor(6 + 4, rect.center().y()).name() == fill.name()
    # The text is drawn in the status colour somewhere in the pill.
    text, _ = pill_colors(SUCCESS)
    colours = {image.pixelColor(x, rect.center().y()).name() for x in range(6, 120)}
    assert any(_close(QColor(c), text) for c in colours)


def _close(a: QColor, b: QColor, tolerance: int = 40) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a.getRgb()[:3], b.getRgb()[:3], strict=True))


def test_draft_and_suspended_are_visually_distinct(theme):
    from cbpos.ui.views.document_view import DocumentBrowserView

    draft = DocumentBrowserView.STATUS_MEANINGS["DRAFT"]
    suspended = DocumentBrowserView.STATUS_MEANINGS["SUSPENDED"]
    assert draft != suspended
    assert pill_colors(draft)[0].name() != pill_colors(suspended)[0].name()
    assert pill_colors(draft)[1].name() != pill_colors(suspended)[1].name()


def test_document_browser_status_column_is_a_pill(db_session):
    from cbpos.ui.views.document_view import DocumentBrowserView

    view = DocumentBrowserView()
    assert isinstance(view.doc_table.itemDelegateForColumn(5), StatusPillDelegate)
    view.populate_table(
        [
            {
                "id": 1,
                "type": "SALE",
                "date": datetime.now(),
                "document_number": "S-1",
                "entity_name": "",
                "total_amount": 1,
                "status": "SUSPENDED",
                "username": "u",
            }
        ]
    )
    item = view.doc_table.item(0, 5)
    assert item.text() == "SUSPENDED"
    assert item.data(STATUS_MEANING_ROLE) == DocumentBrowserView.STATUS_MEANINGS["SUSPENDED"]
    html = view._status_badge_html("VOID")
    assert ("Void" in html or "VOID" in html) and "background-color" in html
    view.deleteLater()


def test_promotions_status_column_is_a_pill(db_session):
    from cbpos.ui.views.promotion_view import PromotionView

    view = PromotionView()
    assert isinstance(view.table.itemDelegateForColumn(6), StatusPillDelegate)
    view.deleteLater()


def test_stock_take_history_status_is_a_pill(db_session):
    from cbpos.ui.views.stock_take_view import _HISTORY_STATUS_MEANINGS, StockTakeView

    view = StockTakeView()
    assert isinstance(view.history_table.itemDelegateForColumn(view.HIST_COL_STATUS), StatusPillDelegate)
    assert len(set(_HISTORY_STATUS_MEANINGS.values())) == len(_HISTORY_STATUS_MEANINGS)
    view.deleteLater()


def test_payment_method_status_pill_sits_next_to_the_name():
    from cbpos.ui.views.payment_methods_view import _MethodCard

    method = MagicMock(spec=PaymentMethod)
    method.name, method.is_cash, method.is_active, method.open_drawer, method.shortcut = (
        "Card",
        False,
        True,
        False,
        None,
    )
    card = _MethodCard(method, MagicMock())
    pill = card.status_label
    buttons = [card.btn_layout.itemAt(i).widget() for i in range(card.btn_layout.count())]
    assert pill not in buttons
    name = card.findChild(type(pill), "PMCardName")
    row = next(
        card.layout().itemAt(0).layout().itemAt(i).layout()
        for i in range(card.layout().itemAt(0).layout().count())
        if card.layout().itemAt(0).layout().itemAt(i).layout() is not None
    )
    widgets = [row.itemAt(i).widget() for i in range(row.count())]
    assert widgets.index(name) + 1 == widgets.index(pill)
    card.deleteLater()


@pytest.mark.parametrize("qss", ["dark.qss", "light.qss"])
def test_payment_method_pill_is_borderless(qss):
    text = (STYLES / qss).read_text(encoding="utf-8")
    for block in re.findall(r"QLabel#PMCardStatus[^{]*\{([^}]*)\}", text):
        assert re.search(r"\bborder\s*:", block) is None
