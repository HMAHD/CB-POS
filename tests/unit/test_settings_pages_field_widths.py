"""
#371: Settings' Sales Tax page already had a proven house convention for
numeric fields (setFixedWidth(200), applied to spin_max_discount,
spin_vat, spin_sscl, spin_sscl_turnover) but four other fields in the
same file skipped it and stretched full-width instead: combo_search_mode,
spin_loyalty_ratio, spin_default_credit (Sales Tax page) and
time_auto_report (Shop Info -> Email tab). Applying the same width that
was already sitting a few lines away closes this out.
"""

import pytest
from PyQt6.QtWidgets import QLineEdit

from cbpos.ui.views.settings_pages import SalesTaxPage, ShopInfoPage

pytestmark = pytest.mark.usefixtures("qapp")

FIELD_WIDTH = 200


class TestSalesTaxPageFieldWidths:
    def test_search_mode_combo_has_the_shared_field_width(self):
        page = SalesTaxPage()
        assert page.combo_search_mode.maximumWidth() == FIELD_WIDTH

    def test_loyalty_ratio_spin_has_the_shared_field_width(self):
        page = SalesTaxPage()
        assert page.spin_loyalty_ratio.maximumWidth() == FIELD_WIDTH

    def test_default_credit_spin_has_the_shared_field_width(self):
        page = SalesTaxPage()
        assert page.spin_default_credit.maximumWidth() == FIELD_WIDTH


class TestShopInfoPageReportTimeWidth:
    def test_report_time_field_has_the_shared_field_width(self):
        page = ShopInfoPage()
        assert page.time_auto_report.maximumWidth() == FIELD_WIDTH


class TestAppearanceTabFieldWidthsAndWidgetType:
    """#370: font size, theme, and language each sized to their own
    content with no shared column ("3 sizes"), and Font Size was a plain
    QSpinBox -- the native-stepper widget already known to break under
    this app's QSS in several other places. Give all three the same
    house-convention width and replace the spinbox with the QLineEdit +
    validator pattern already proven in product_editor.py."""

    def test_font_size_is_a_line_edit_not_a_spinbox(self):
        page = ShopInfoPage()
        assert isinstance(page.spin_font_size, QLineEdit)

    def test_font_size_rejects_out_of_range_values(self):
        page = ShopInfoPage()
        validator = page.spin_font_size.validator()
        assert validator is not None
        assert validator.bottom() == 8
        assert validator.top() == 24

    def test_font_size_theme_and_language_share_the_same_width(self):
        page = ShopInfoPage()
        assert page.spin_font_size.maximumWidth() == FIELD_WIDTH
        assert page.combo_theme.maximumWidth() == FIELD_WIDTH
        assert page.combo_language.maximumWidth() == FIELD_WIDTH

    def test_font_size_loads_and_saves_as_an_integer(self):
        page = ShopInfoPage()
        page.load({"font_size": 18})
        assert page.spin_font_size.text() == "18"
        assert page.save()["font_size"] == 18
