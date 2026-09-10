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
