"""
#542 ([REC-07]): Reports: favorite/pinned reports.
- Show a Favorites group at the top of the Reports sidebar.
- Starring a report adds it to Favorites, persisted across restarts.
- Unstarring removes it, updating the sidebar and persisting.
- Language switching updates Favorites category label and tooltips.
- VAT filtering applies to favorites.
"""

import pytest
from PyQt6.QtWidgets import QLabel, QPushButton

from cbpos.core.reports import register_all_reports
from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import get_language, set_language
from cbpos.ui.views.reports.report_viewer import ReportViewer

pytestmark = [pytest.mark.usefixtures("qapp", "db_session")]


@pytest.fixture(autouse=True)
def clean_favorites():
    """Ensure favorite_reports is cleared before and after each test."""
    original = ConfigService.get("favorite_reports")
    ConfigService.set("favorite_reports", [])
    yield
    ConfigService.set("favorite_reports", original if isinstance(original, list) else [])


@pytest.fixture
def language():
    """Switch language inside a test and restore the original afterwards."""
    orig = get_language()
    yield set_language
    set_language(orig)


def _category_labels(viewer: ReportViewer) -> list[str]:
    return [label.text() for label in viewer.findChildren(QLabel, "ReportCategoryLabel")]


def _nav_buttons(viewer: ReportViewer) -> list[QPushButton]:
    return viewer.findChildren(QPushButton, "ReportNavItem")


class TestFavoriteReports:
    def test_no_favorites_group_when_none_starred(self):
        register_all_reports()
        viewer = ReportViewer()

        labels = _category_labels(viewer)
        assert "Favorites" not in labels
        assert labels == ["Sales", "Inventory", "Financial", "Audit"]

    def test_starring_report_adds_favorites_group_at_top(self):
        register_all_reports()
        viewer = ReportViewer()
        viewer.show()

        # Open daily sales summary report
        btn = next(b for b in _nav_buttons(viewer) if b.property("report_id") == "daily_sales_summary")
        btn.click()

        assert viewer.current_report.id == "daily_sales_summary"
        assert viewer.btn_favorite.isVisible()
        assert "daily_sales_summary" not in ConfigService.get("favorite_reports")

        # Click the star button to favorite
        viewer.btn_favorite.click()

        # Persisted in ConfigService
        saved = ConfigService.get("favorite_reports")
        assert "daily_sales_summary" in saved

        # Favorites category is now the first category in the sidebar
        labels = _category_labels(viewer)
        assert labels[0] == "Favorites"
        assert labels[1:] == ["Sales", "Inventory", "Financial", "Audit"]

        # Favorites count badge is 1
        count_labels = viewer.findChildren(QLabel, "ReportCategoryCount")
        assert count_labels[0].text() == "1"

        # The report button in Favorites exists and is starred
        fav_btns = [b for b in _nav_buttons(viewer) if b.property("report_id") == "daily_sales_summary"]
        assert len(fav_btns) >= 2  # One in Favorites, one in Sales
        assert not fav_btns[0].icon().isNull()

    def test_favorites_persist_across_restarts(self):
        register_all_reports()
        # Seed ConfigService with two favorites
        ConfigService.set("favorite_reports", ["daily_sales_summary", "inventory_valuation"])

        # Create fresh viewer (simulating app restart)
        viewer = ReportViewer()

        labels = _category_labels(viewer)
        assert labels[0] == "Favorites"
        assert labels[1:] == ["Sales", "Inventory", "Financial", "Audit"]

        count_labels = viewer.findChildren(QLabel, "ReportCategoryCount")
        assert count_labels[0].text() == "2"

        # Both reports appear under Favorites in the order they were starred
        first_category_btns = _nav_buttons(viewer)[:2]
        assert [b.property("report_id") for b in first_category_btns] == [
            "daily_sales_summary",
            "inventory_valuation",
        ]

    def test_unstarring_report_removes_it_from_favorites(self):
        register_all_reports()
        ConfigService.set("favorite_reports", ["daily_sales_summary"])

        viewer = ReportViewer()
        assert _category_labels(viewer)[0] == "Favorites"

        # Open the report and click the star button to unstar
        fav_btn = next(b for b in _nav_buttons(viewer) if b.property("report_id") == "daily_sales_summary")
        fav_btn.click()

        viewer.btn_favorite.click()

        assert "daily_sales_summary" not in ConfigService.get("favorite_reports")
        labels = _category_labels(viewer)
        assert "Favorites" not in labels
        assert labels == ["Sales", "Inventory", "Financial", "Audit"]

    def test_clicking_favorite_button_keeps_report_open(self):
        register_all_reports()
        viewer = ReportViewer()
        viewer.show()

        btn = next(b for b in _nav_buttons(viewer) if b.property("report_id") == "daily_sales_summary")
        btn.click()

        # Star it
        viewer.btn_favorite.click()
        assert viewer.current_report.id == "daily_sales_summary"
        assert viewer.report_header.isVisible()

        # Unstar it
        viewer.btn_favorite.click()
        assert viewer.current_report.id == "daily_sales_summary"
        assert viewer.report_header.isVisible()

    def test_context_menu_toggles_favorite(self):
        register_all_reports()
        viewer = ReportViewer()

        # Toggle via helper method that context menu calls
        viewer._toggle_favorite_by_id("daily_sales_summary")
        assert "daily_sales_summary" in ConfigService.get("favorite_reports")
        assert _category_labels(viewer)[0] == "Favorites"

        viewer._toggle_favorite_by_id("daily_sales_summary")
        assert "daily_sales_summary" not in ConfigService.get("favorite_reports")
        assert "Favorites" not in _category_labels(viewer)

    def test_language_switch_updates_favorites_label_and_tooltip(self, language):
        language("en")
        register_all_reports()
        ConfigService.set("favorite_reports", ["daily_sales_summary"])

        viewer = ReportViewer()
        assert _category_labels(viewer)[0] == "Favorites"

        # Switch to Sinhala
        language("si")
        assert _category_labels(viewer)[0] == "ප්‍රියතම"

        # Switch to Tamil
        language("ta")
        assert _category_labels(viewer)[0] == "விருப்பமானவை"

    def test_vat_inactive_hides_vat_reports_from_favorites(self, monkeypatch):
        register_all_reports()
        # tax_liability is a VAT-only report
        ConfigService.set("favorite_reports", ["tax_liability", "daily_sales_summary"])

        # When VAT registered is False:
        monkeypatch.setattr("cbpos.core.services.tax_service.TaxService.is_vat_active", lambda: False)
        viewer = ReportViewer()

        fav_btns = [
            b for b in _nav_buttons(viewer) if b.property("report_id") in {"tax_liability", "daily_sales_summary"}
        ]
        fav_ids_in_sidebar = {b.property("report_id") for b in fav_btns}
        assert "tax_liability" not in fav_ids_in_sidebar
        assert "daily_sales_summary" in fav_ids_in_sidebar

        # Count badge shows 1 (only daily_sales_summary)
        count_labels = viewer.findChildren(QLabel, "ReportCategoryCount")
        assert count_labels[0].text() == "1"

        # When VAT is active:
        monkeypatch.setattr("cbpos.core.services.tax_service.TaxService.is_vat_active", lambda: True)
        viewer_vat = ReportViewer()
        count_labels_vat = viewer_vat.findChildren(QLabel, "ReportCategoryCount")
        assert count_labels_vat[0].text() == "2"
