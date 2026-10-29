"""
#588: in the Sales order bar, the long Sinhala label ("ඇණවුම් කළමනාකරණය")
was reported running into the "දැන්" (Current) tab next to it. The label
now keeps exactly its text width and the tab strip alone takes the spare
width, so in en/si/ta at 1366 and 1024 wide nothing overlaps.
"""

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication

from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import get_language, set_language
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def make_view(qapp, db_session, monkeypatch):
    monkeypatch.setattr(ThemeService, "theme_change_callbacks", [])
    monkeypatch.setattr(ThemeService, "current_theme", ThemeService.current_theme)
    captured: list[str] = []
    monkeypatch.setattr(ThemeService, "_set_stylesheet", captured.append)
    ThemeService.apply_theme("Dark")
    monkeypatch.setattr(SalesView, "_printer_notice_shown", True)
    original_lang = get_language()
    views: list[SalesView] = []

    def _make(lang: str, width: int) -> SalesView:
        set_language(lang)
        v = SalesView()
        v.setStyleSheet(captured[-1])
        v.resize(width, 768)
        v.show()
        for _ in range(3):
            QApplication.processEvents()
        views.append(v)
        return v

    yield _make
    set_language(original_lang)
    for v in views:
        v.hide()
        v.deleteLater()


def _rect(bar, widget) -> QRect:
    return QRect(widget.mapTo(bar, widget.rect().topLeft()), widget.size())


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
@pytest.mark.parametrize("width", [1366, 1024])
def test_order_bar_label_and_buttons_do_not_overlap(make_view, lang, width):
    bar = make_view(lang, width).order_bar
    label = _rect(bar, bar.lbl_title)
    tabs = _rect(bar, bar.scroll_area)
    new_btn = _rect(bar, bar.btn_new)
    current_tab = bar.tabs_layout.itemAt(0).widget()

    assert bar.lbl_title.width() >= bar.lbl_title.sizeHint().width(), "label squeezed below its text width"
    assert label.right() < tabs.left()
    assert _rect(bar, current_tab).left() > label.right()
    assert tabs.right() < new_btn.left()
    assert new_btn.right() <= bar.width()
