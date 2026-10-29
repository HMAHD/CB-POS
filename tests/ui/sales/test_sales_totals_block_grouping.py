"""Unit tests for Issue #536 ([REC-02]): Sales totals block grouping.

Verifies:
1. SalesView.total_widget has objectName 'TotalWidget' and encapsulates the totals.
2. TotalLabel and GrandTotalCaption reside inside total_widget.
3. GrandTotalCaption updates its uppercase localized text on language switch.
4. TotalWidget is styled as an enclosed card panel in both Dark and Light themes.
"""

import pytest
from PyQt6.QtWidgets import QApplication

from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t, set_language
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def sales_view(db_session):
    view = SalesView()
    yield view
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def test_sales_totals_panel_structure(sales_view):
    """Verify total_widget encapsulates subtotal and grand total elements."""
    assert hasattr(sales_view, "total_widget")
    assert sales_view.total_widget.objectName() == "TotalWidget"

    # Grand total caption and total label
    assert hasattr(sales_view, "lbl_grand_total_title")
    assert sales_view.lbl_grand_total_title.objectName() == "GrandTotalCaption"
    assert sales_view.lbl_grand_total_title.text() == _t("cart.header_total").upper()

    assert sales_view.total_label.objectName() == "TotalLabel"
    assert sales_view.total_label.parentWidget() == sales_view.total_widget
    assert sales_view.lbl_grand_total_title.parentWidget() == sales_view.total_widget


def test_sales_totals_caption_retranslates(sales_view):
    """Verify GrandTotalCaption retranslates across English, Sinhala, and Tamil."""
    for lang in ["en", "si", "ta", "en"]:
        set_language(lang)
        QApplication.processEvents()
        expected = _t("cart.header_total").upper()
        assert sales_view.lbl_grand_total_title.text() == expected


def test_total_widget_and_caption_styled_in_both_themes():
    """Verify TotalWidget and GrandTotalCaption styles exist in Dark and Light stylesheets."""
    for theme_name in ["Dark", "Light"]:
        captured = []
        ThemeService.set_stylesheet_handler(captured.append)
        ThemeService.apply_theme(theme_name)
        assert len(captured) > 0
        css = captured[-1]

        assert "QWidget#TotalWidget" in css
        assert "border-radius: 8px" in css
        assert "QLabel#GrandTotalCaption" in css
