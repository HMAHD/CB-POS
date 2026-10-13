"""Tests for moving remaining hardcoded English UI strings into i18n (#585).

Verifies:
1. 'common.na' localization in 'si' and 'ta', and usage in PriceListView and DocumentBrowserView.
2. Settings SecurityPage spin suffixes ('min', 'sec', 'backups') localized and updated in retranslate_ui().
3. Report print HTML header and timestamp localization in report_viewer.py.
4. Stock Take duplicate product error message localization.
"""

from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.models import PriceList
from cbpos.i18n import get_language, set_language, unregister_language_callback
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.views.settings_pages import SystemPage
from cbpos.ui.views.stock_take_view import StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def restore_language():
    prev_lang = get_language()
    yield
    set_language(prev_lang)


def test_na_localization_and_usage(db_session):
    """Verify common.na is translated in si and ta and used in PriceList and DocumentBrowser."""
    set_language("si")
    from cbpos.i18n import _t

    assert _t("common.na") == "අදාළ නොවේ"

    set_language("ta")
    assert _t("common.na") == "பொருந்தாது"

    # PriceListView: date range with no dates shows translated N/A
    set_language("si")
    pl = PriceList(name="Test PL", start_date=None, end_date=None)
    view_pl = PriceListView()
    try:
        view_pl._on_nav_clicked(pl)
        assert "අදාළ නොවේ" in view_pl.lbl_dates.text()
        assert "N/A" not in view_pl.lbl_dates.text()
    finally:
        unregister_language_callback(view_pl.retranslate_ui)
        view_pl.deleteLater()

    # DocumentBrowserView: doc with no date shows translated N/A
    view_doc = DocumentBrowserView()
    try:
        doc = {
            "id": 1,
            "type": "sale",
            "document_number": "INV-001",
            "date": None,
            "status": "COMPLETED",
        }
        view_doc.display_details(doc)
        assert "අදාළ නොවේ" in view_doc.details_label.text()
        assert "N/A" not in view_doc.details_label.text()
    finally:
        unregister_language_callback(view_doc.retranslate_ui)
        view_doc.deleteLater()


def test_settings_security_spin_suffixes_localized():
    """Verify SystemPage spin suffixes update on language switch and retranslate_ui."""
    page = SystemPage()
    try:
        set_language("en")
        page.retranslate_ui()
        assert page.spin_timeout.suffix() == " min"
        assert page.spin_lockout.suffix() == " sec"
        assert page.spin_retention.suffix() == " backups"

        set_language("si")
        page.retranslate_ui()
        assert page.spin_timeout.suffix() == " මිනි"
        assert page.spin_lockout.suffix() == " තත්"
        assert page.spin_retention.suffix() == " උපස්ථ"

        set_language("ta")
        page.retranslate_ui()
        assert page.spin_timeout.suffix() == " நிமி"
        assert page.spin_lockout.suffix() == " விநாடி"
        assert page.spin_retention.suffix() == " காப்புப்பிரதிகள்"
    finally:
        unregister_language_callback(page.retranslate_ui)
        page.deleteLater()


def test_report_print_html_localized():
    """Verify print_report HTML header and date labels are localized."""
    set_language("si")
    import pandas as pd

    viewer = ReportViewer()
    try:
        mock_report = MagicMock()
        mock_report.name = "Sales Summary"
        viewer.current_report = mock_report
        viewer._full_df = pd.DataFrame({"Item": ["A"], "Total": [100]})

        captured_html = []

        def mock_set_html(self, html):
            captured_html.append(html)

        with (
            patch("PyQt6.QtPrintSupport.QPrintDialog.exec", return_value=1),
            patch("PyQt6.QtGui.QTextDocument.setHtml", mock_set_html),
            patch("PyQt6.QtGui.QTextDocument.print"),
        ):
            viewer.print_report()

        assert len(captured_html) == 1
        html = captured_html[0]
        assert "ජනනය කළ දිනය:" in html
        assert "Generated on:" not in html
    finally:
        unregister_language_callback(viewer.retranslate_ui)
        viewer.deleteLater()


def test_stock_take_duplicate_product_message_localized(db_session, monkeypatch):
    """Verify Stock Take duplicate product error message is localized."""
    set_language("si")
    warnings = []
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.warning", lambda *a, **k: warnings.append(a[2]))

    view = StockTakeView()
    try:
        view.current_stock_count = MagicMock()
        view.current_stock_count.id = 1
        view.item_model = MagicMock()
        view.item_model.items = []

        # Product already in count triggers localized message
        with patch(
            "cbpos.core.services.stock_count_service.StockCountService.add_single_item",
            side_effect=ValueError("Product already in this stock count."),
        ):
            with patch("cbpos.core.services.product_service.ProductService.get_by_barcode", return_value=MagicMock()):
                view._count_product("123456")

        assert len(warnings) == 1
        assert "දැනටමත් මෙම තොග ගණන් කිරීමට එකතු කර ඇත" in warnings[0]
        assert "Product already in this stock count." not in warnings[0]
    finally:
        unregister_language_callback(view.retranslate_ui)
        view.deleteLater()
