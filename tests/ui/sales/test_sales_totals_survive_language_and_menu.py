"""
#602: with items in the cart, the totals panel, Pay and every cart column
must stay visible through language switches and side-menu toggles.

What reproduced (offscreen, 1366x768):
- Opening the side menu hid the action panel, so the splitter re-flowed
  the cart to the full window width -- right under the 300px menu
  overlay. The Price/Qty/Disc/Total columns and the grand total ended up
  beneath the menu: "only the ITEM header shows" / "totals missing while
  the side menu is open".
- The no-printer notice (#623) and the cart splitter shared the main
  layout's spare height (both Preferred, no stretch), so the one-line
  notice ballooned to ~190px (~280px with the menu open), squeezing the
  cart and totals.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication

from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import get_language, set_language
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView


def _make_product(product_id: int) -> MagicMock:
    product = MagicMock()
    product.id = product_id
    product.name_en = f"Test Product {product_id}"
    product.barcode = f"TEST{product_id:03d}"
    product.price = Decimal("200.00")
    product.stock_qty = Decimal("10")
    product.unit = None
    product.is_age_restricted = False
    return product


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session, monkeypatch):
    monkeypatch.setattr(ThemeService, "theme_change_callbacks", [])
    monkeypatch.setattr(ThemeService, "current_theme", ThemeService.current_theme)
    captured: list[str] = []
    monkeypatch.setattr(ThemeService, "_set_stylesheet", captured.append)
    ThemeService.apply_theme("Dark")
    monkeypatch.setattr(SalesView, "_printer_notice_shown", True)  # shown explicitly below

    original_lang = get_language()
    v = SalesView()
    v.setStyleSheet(captured[-1])
    v.resize(1366, 768)
    v.show()
    for i in range(1, 4):
        v.cart_service.add_item(_make_product(i))
    v.update_cart_display()
    _settle()
    yield v
    set_language(original_lang)
    v.menu_animation.stop()
    v.hide()
    v.deleteLater()


def _settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


def _rect_in_view(view: SalesView, widget) -> QRect:
    return QRect(widget.mapTo(view, widget.rect().topLeft()), widget.size())


def _assert_totals_and_columns_visible(view: SalesView) -> None:
    totals = view.total_label.parentWidget()
    assert totals.isVisible()
    assert totals.height() > 0
    assert view.rect().contains(_rect_in_view(view, totals)), "totals panel runs off the window"

    # Anything under the open side menu is hidden from the cashier.
    covered_from = view.side_menu.x() if view.side_menu.isVisible() else view.width()
    assert _rect_in_view(view, view.total_label).right() < covered_from, "grand total is under the side menu"

    header = view.cart_table.horizontalHeader()
    table_x = view.cart_table.viewport().mapTo(view, view.cart_table.viewport().rect().topLeft()).x()
    for col in range(view.cart_table.columnCount()):
        assert view.cart_table.horizontalHeaderItem(col).text(), f"column {col} has no header text"
        assert not header.isSectionHidden(col)
        right = table_x + header.sectionViewportPosition(col) + header.sectionSize(col)
        assert right <= covered_from, f"column {col} header is under the side menu"


def _finish_menu_animation(view: SalesView) -> None:
    view.menu_animation.setCurrentTime(view.menu_animation.duration())
    _settle()


def test_totals_and_columns_survive_five_language_switches(view):
    for lang in ["si", "en", "ta", "si", "en"]:
        set_language(lang)
        _settle()
        _assert_totals_and_columns_visible(view)
        assert view.action_panel.btn_pay.isVisible()


def test_totals_and_columns_survive_ten_side_menu_toggles(view):
    for _ in range(10):
        view.toggle_side_menu()
        _finish_menu_animation(view)
        _assert_totals_and_columns_visible(view)
    assert not view.side_menu.isVisible()
    assert view.action_panel.btn_pay.isVisible()


def test_printer_notice_takes_only_the_height_it_needs(view):
    view._show_printer_notice()
    _settle()
    notice = view.printer_notice
    assert notice.height() <= notice.sizeHint().height() + 4
    _assert_totals_and_columns_visible(view)

    view.toggle_side_menu()
    _finish_menu_animation(view)
    assert notice.height() <= notice.sizeHint().height() + 4
    _assert_totals_and_columns_visible(view)
