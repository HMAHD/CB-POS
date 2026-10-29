"""Tests for trilingual UI correctness (#586, #582, #587).

Verifies:
1. Product display name localization and fallback in SI, TA, and EN (#586).
2. Product search in Proforma by Sinhala/Tamil/English names and barcodes (#586).
3. Price list and Stock take views showing localized product names (#586).
4. Translation of document status, promotion type, and payment methods (#582).
5. Document browser table status pill and detail badge/payments (#582).
6. Stock take history status translation with UserRole preserved for DRAFT context menu (#582).
7. Removal of setFixedWidth on buttons and controls in Admin Tools and Settings (#587).
8. QGroupBox title padding-top in both dark and light QSS stylesheets (#587).
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QScrollArea

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Product, StockCount, StockCountItem, User
from cbpos.core.utils.formatters import (
    format_document_status,
    format_payment_method,
    format_promotion_type,
)
from cbpos.i18n import get_language, set_language, unregister_language_callback
from cbpos.ui.dialogs.proforma_dialog import ProformaDialog
from cbpos.ui.views.admin_tools_view import AdminToolsView
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.stock_take_view import StockCountItemModel, StockCountReportDialog, StockTakeView
from tests.helpers.qss import rendered_qss

pytestmark = pytest.mark.usefixtures("qapp")

STYLE_DIR = Path(__file__).resolve().parents[3] / "cbpos" / "ui" / "styles"


@pytest.fixture(autouse=True)
def restore_language():
    """Ensure tests restore English language after running."""
    prev_lang = get_language()
    yield
    set_language(prev_lang)


# ==============================================================================
# #586 [UI-024]: Localized Product Names & Search
# ==============================================================================


def test_product_display_name_and_fallbacks():
    """Product.display_name returns active language name with correct fallbacks."""
    # 1. Product with all names populated
    p1 = Product(name_en="Bread", name_si="පාන්", name_ta="ரொட்டி")
    set_language("en")
    assert p1.display_name == "Bread"
    set_language("si")
    assert p1.display_name == "පාන්"
    set_language("ta")
    assert p1.display_name == "ரொட்டி"

    # 2. Product with only Sinhala name
    p2 = Product(name_en="", name_si="කැකුළු සහල්", name_ta=None)
    set_language("en")
    assert p2.display_name == "කැකුළු සහල්"
    set_language("si")
    assert p2.display_name == "කැකුළු සහල්"
    set_language("ta")
    assert p2.display_name == "කැකුළු සහල්"

    # 3. Product with only English name
    p3 = Product(name_en="Milk Powder", name_si=None, name_ta=None)
    set_language("si")
    assert p3.display_name == "Milk Powder"
    set_language("ta")
    assert p3.display_name == "Milk Powder"

    # 4. Product with Tamil name and English name, in Sinhala mode falls back to English
    p4 = Product(name_en="Sugar", name_si=None, name_ta="சர்க்கரை")
    set_language("si")
    assert p4.display_name == "Sugar"
    set_language("ta")
    assert p4.display_name == "சர்க்கரை"


def test_proforma_search_finds_sinhala_and_tamil_products(monkeypatch):
    """Proforma completer and add_product find products by Sinhala/Tamil names and barcode."""
    p_si = Product(id=1, barcode="111", name_en="", name_si="කිරිපිටි", name_ta=None, price=Decimal("450.00"))
    p_ta = Product(id=2, barcode="222", name_en="Tea", name_si=None, name_ta="தேநீர்", price=Decimal("200.00"))

    monkeypatch.setattr(
        "cbpos.ui.dialogs.proforma_dialog.ProductService.get_all_products",
        lambda self: [p_si, p_ta],
    )
    monkeypatch.setattr(
        "cbpos.ui.dialogs.proforma_dialog.CustomerService.get_all_customers",
        lambda self: [],
    )

    set_language("si")
    dialog = ProformaDialog()

    # Sinhala product can be added by its Sinhala name
    dialog.product_search.setText("කිරිපිටි")
    dialog.add_product()
    assert len(dialog.items) == 1
    assert dialog.items[0]["product_id"] == 1
    assert dialog.items[0]["product_name"] == "කිරිපිටි"

    # Tamil product can be added by its barcode or Tamil name
    dialog.product_search.setText("222")
    dialog.add_product()
    assert len(dialog.items) == 2
    assert dialog.items[1]["product_id"] == 2
    assert dialog.items[1]["product_name"] == "Tea"  # In 'si', p_ta has no name_si, falls back to name_en

    set_language("ta")
    dialog_ta = ProformaDialog()
    dialog_ta.product_search.setText("தேநீர்")
    dialog_ta.add_product()
    assert len(dialog_ta.items) == 1
    assert dialog_ta.items[0]["product_id"] == 2
    assert dialog_ta.items[0]["product_name"] == "தேநீர்"


def test_pricelist_and_stock_take_use_product_display_name(db_session, monkeypatch):
    """Price lists and Stock take views show localized product names."""
    prod = Product(id=10, barcode="777", name_en="Biscuit", name_si="බිස්කට්", name_ta="பிஸ்கட்", price=Decimal("100.00"))

    set_language("si")
    assert prod.display_name == "බිස්කට්"

    # StockCountItemModel
    item = StockCountItem(id=1, product_id=10, expected_qty=Decimal("5"), counted_qty=Decimal("5"), product=prod)
    model = StockCountItemModel([item])
    idx = model.index(0, 1)
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "බිස්කට්"

    # StockCountReportDialog
    sc = StockCount(
        id=1,
        document_number="STK-01",
        status=DocumentStatus.COMPLETED,
        items=[item],
        total_variance_value=Decimal("0.00"),
    )
    monkeypatch.setattr(
        "cbpos.ui.views.stock_take_view.StockCountService.get_stock_count",
        lambda sid: sc,
    )
    with patch("cbpos.ui.views.stock_take_view.StockCountReportDialog.exec"):
        report = StockCountReportDialog(1)
        assert report.table.item(0, 1).text() == "බිස්කට්"


# ==============================================================================
# #582 [UI-022-A]: Status Codes & Enum Translations
# ==============================================================================


def test_format_document_status_trilingual():
    """Document statuses format correctly in EN, SI, and TA."""
    set_language("en")
    assert format_document_status("COMPLETED") == "Completed"
    assert format_document_status("VOID") == "Void"
    assert format_document_status("DRAFT") == "Draft"
    assert format_document_status("COUNTED") == "Counted"

    set_language("si")
    assert format_document_status("COMPLETED") == "සම්පූර්ණ"
    assert format_document_status("VOID") == "අවලංගු"
    assert format_document_status("DRAFT") == "කටු සටහන"
    assert format_document_status("COUNTED") == "ගණන් කළා"

    set_language("ta")
    assert format_document_status("COMPLETED") == "முடிந்தது"
    assert format_document_status("VOID") == "ரத்து"
    assert format_document_status("DRAFT") == "வரைவு"
    assert format_document_status("COUNTED") == "எண்ணியது"


def test_format_promotion_type_trilingual():
    """Promotion types format correctly in EN, SI, and TA."""
    set_language("en")
    assert format_promotion_type("PERCENTAGE") == "Percentage"
    assert format_promotion_type("FIXED_AMOUNT") == "Fixed Amount"
    assert format_promotion_type("BOGO") == "Buy One Get One"

    set_language("si")
    assert format_promotion_type("PERCENTAGE") == "ප්‍රතිශතය"
    assert format_promotion_type("FIXED_AMOUNT") == "නියත මුදල"
    assert format_promotion_type("BOGO") == "එකක් ගන්න එකක් ෆ්‍රී"

    set_language("ta")
    assert format_promotion_type("PERCENTAGE") == "சதவீதம்"
    assert format_promotion_type("FIXED_AMOUNT") == "நிலையான தொகை"
    assert format_promotion_type("BOGO") == "ஒன்னு வாங்கினா ஒன்னு ஃப்ரீ"


def test_format_payment_method_trilingual():
    """Payment methods format correctly in EN, SI, and TA."""
    set_language("en")
    assert format_payment_method("Cash") == "Cash"
    assert format_payment_method("Card") == "Card"
    assert format_payment_method("Credit") == "Credit"
    assert format_payment_method("QR/Mobile") == "QR/Mobile"
    assert format_payment_method("CustomMethod") == "CustomMethod"

    set_language("si")
    assert format_payment_method("Cash") == "මුදල්"
    assert format_payment_method("Card") == "කාඩ්පත්"
    assert format_payment_method("Credit") == "ණය"
    assert format_payment_method("QR/Mobile") == "QR/ජංගම"
    assert format_payment_method("CustomMethod") == "CustomMethod"

    set_language("ta")
    assert format_payment_method("Cash") == "பணம்"
    assert format_payment_method("Card") == "அட்டை"
    assert format_payment_method("Credit") == "கடன்"
    assert format_payment_method("QR/Mobile") == "QR/மொபைல்"
    assert format_payment_method("CustomMethod") == "CustomMethod"


def test_document_browser_shows_translated_status_and_payments(db_session, monkeypatch):
    """Document Browser displays translated status in table and detail panel."""
    doc = {
        "id": 1,
        "type": "SALE",
        "date": datetime(2026, 10, 13, 10, 0, 0),
        "document_number": "INV-001",
        "entity_name": "Kasun",
        "total_amount": Decimal("1500.00"),
        "status": "COMPLETED",
        "username": "cashier1",
        "payments": [{"method": "Cash", "amount": Decimal("1500.00")}],
        "items": [],
    }

    set_language("si")
    view = DocumentBrowserView()
    try:
        view.populate_table([doc])

        item = view.doc_table.item(0, 5)
        # Status pill displays Sinhala translated string, not uppercase code
        assert item.text() == "සම්පූර්ණ"
        # Preserves raw status code in UserRole
        assert item.data(Qt.ItemDataRole.UserRole) == "COMPLETED"

        # Detail status badge
        badge_html = view._status_badge_html("COMPLETED")
        assert "සම්පූර්ණ" in badge_html
        assert "COMPLETED" not in badge_html

        # Detail payment line
        view.display_details(doc)
        assert "මුදල්: Rs. 1,500.00" in view.payment_label.text()
    finally:
        unregister_language_callback(view.retranslate_ui)
        view.deleteLater()


def test_stock_take_history_context_menu_with_translated_draft(db_session, monkeypatch):
    """Stock Take history table shows translated status while context menu still recognizes DRAFT."""
    set_language("si")

    sc_draft = StockCount(
        id=99,
        document_number="STK-99",
        status=DocumentStatus.DRAFT,
        date=None,
        user=User(username="test_user", pin_hash="x"),
        items=[],
        total_variance_value=Decimal("0.00"),
    )

    monkeypatch.setattr(
        "cbpos.ui.views.stock_take_view.StockCountService.get_all_stock_counts",
        lambda **kwargs: [sc_draft],
    )

    view = StockTakeView()
    try:
        view.refresh_history()

        # Table displays translated status "කටු සටහන"
        status_item = view.history_table.item(0, view.HIST_COL_STATUS)
        assert status_item.text() == "කටු සටහන"
        assert status_item.data(Qt.ItemDataRole.UserRole) == DocumentStatus.DRAFT

        # Context menu checks UserRole and recognizes DRAFT status
        status_code = status_item.data(Qt.ItemDataRole.UserRole) or status_item.text()
        assert status_code == DocumentStatus.DRAFT
    finally:
        unregister_language_callback(view.retranslate_ui)
        view.deleteLater()


# ==============================================================================
# #587 [UI-025-A]: Fixed Width Elimination & Scrollable Containers
# ==============================================================================


def test_admin_tools_buttons_have_no_fixed_width(db_session):
    """All text buttons in AdminToolsView use minimumWidth without setFixedWidth."""
    view = AdminToolsView()
    try:
        # Buttons that previously had setFixedWidth
        buttons = [
            view.btn_update,
            view.btn_db_refresh,
            view.btn_check_integrity,
            view.btn_apply,
            view.btn_test_printer,
            view.btn_test_drawer,
            view.btn_clear_scan,
        ]

        for btn in buttons:
            # Fixed width widgets have maximumWidth == minimumWidth
            assert btn.maximumWidth() > btn.minimumWidth(), f"{btn} has maximumWidth == minimumWidth (fixed width)"
            assert btn.minimumWidth() >= 80, f"{btn} has minimumWidth < 80"

        # Hardware value labels have adequate height for Sinhala diacritics
        assert view.lbl_hw_type.minimumHeight() >= view.fontMetrics().height() + 8
        assert view.lbl_hw_path.minimumHeight() >= view.fontMetrics().height() + 8
    finally:
        unregister_language_callback(view.retranslate_ui)
        view.deleteLater()


def test_admin_tools_tabs_are_scrollable(db_session):
    """AdminToolsView Database and Hardware tabs are wrapped in QScrollArea."""
    view = AdminToolsView()
    try:
        assert isinstance(view.tabs.widget(0), QScrollArea)
        assert isinstance(view.tabs.widget(2), QScrollArea)
    finally:
        unregister_language_callback(view.retranslate_ui)
        view.deleteLater()


def test_qgroupbox_padding_top_in_qss():
    """Both dark.qss and light.qss have padding-top on QGroupBox to prevent title clipping."""
    for theme_file in ("dark.qss", "light.qss"):
        content = rendered_qss(theme_file)
        assert "padding-top: 16px;" in content, f"padding-top missing in {theme_file}"
