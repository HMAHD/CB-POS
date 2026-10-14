"""
#541: each report's category was its *translated* name, used as the
registry key once at startup and sorted alphabetically -- so the sidebar
order differed per language, stayed in the startup language after a
switch, and was never rebuilt when VAT was turned on or off.

Categories are now stable IDs in a fixed business order (Sales first),
translated only when the sidebar is drawn.
"""

import pytest
from PyQt6.QtWidgets import QLabel, QPushButton

from cbpos.core.reports import register_all_reports
from cbpos.core.reports.registry import ReportRegistry
from cbpos.i18n import get_language, set_language, translate_in
from cbpos.ui.views.reports.report_viewer import ReportViewer

FIXED_ORDER = ["sales", "inventory", "financial", "audit"]


@pytest.fixture
def language():
    """Switch language inside a test and restore the original afterwards."""
    original = get_language()
    yield set_language
    set_language(original)


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_category_order_is_the_same_in_every_language(language, lang):
    language(lang)
    register_all_reports()

    assert ReportRegistry().get_all_categories() == FIXED_ORDER


def _category_labels(viewer) -> list[str]:
    return [label.text() for label in viewer.findChildren(QLabel, "ReportCategoryLabel")]


@pytest.mark.usefixtures("qapp", "db_session")
def test_sidebar_shows_category_names_in_business_order(language):
    language("en")
    register_all_reports()

    viewer = ReportViewer()

    assert _category_labels(viewer) == ["Sales", "Inventory", "Financial", "Audit"]


def _nav_items(viewer) -> list[QPushButton]:
    return viewer.findChildren(QPushButton, "ReportNavItem")


@pytest.mark.usefixtures("qapp", "db_session")
def test_switching_language_updates_category_names(language):
    language("en")
    register_all_reports()
    viewer = ReportViewer()

    language("si")

    assert _category_labels(viewer) == ["විකුණුම්", "තොග", "මූල්‍ය", "විගණනය"]


@pytest.mark.usefixtures("qapp", "db_session")
def test_switching_language_updates_report_names(language):
    language("en")
    register_all_reports()
    viewer = ReportViewer()

    language("ta")

    names = {btn.property("report_id"): btn.text() for btn in _nav_items(viewer)}
    assert names["daily_sales_summary"] == translate_in("ta", "reports.daily_sales_summary")


@pytest.mark.usefixtures("qapp", "db_session")
def test_selected_report_stays_selected_after_language_switch(language):
    language("en")
    register_all_reports()
    viewer = ReportViewer()
    next(b for b in _nav_items(viewer) if b.property("report_id") == "low_stock").click()

    language("si")

    checked = [b.property("report_id") for b in _nav_items(viewer) if b.isChecked()]
    assert checked == ["low_stock"]
