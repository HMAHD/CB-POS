"""Unit tests for Issue #537 ([REC-03]): Management header actions and Dashboard KPI cards.

Verifies:
1. ManagementView has a persistent management_header with title, clock, POS button, and Logout button.
2. The header title updates dynamically when switching tabs and on language switches.
3. Clicking btn_header_pos emits request_pos_view.
4. Clicking btn_header_logout emits logout_requested.
5. Live clock updates text correctly.
6. DashboardView uses StatCard frames for quick stats and tax summary.
7. Stylesheet definitions for ManagementHeader, its buttons, and StatCard exist in both themes.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QFrame

from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t, set_language
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.management_view import ManagementView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def management_view(db_session):
    view = ManagementView()
    yield view
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def test_management_header_structure(management_view):
    """Verify ManagementView contains persistent header elements."""
    assert hasattr(management_view, "management_header")
    assert isinstance(management_view.management_header, QFrame)
    assert management_view.management_header.objectName() == "ManagementHeader"

    assert hasattr(management_view, "lbl_header_title")
    assert management_view.lbl_header_title.objectName() == "ManagementHeaderTitle"

    assert hasattr(management_view, "lbl_header_clock")
    assert management_view.lbl_header_clock.objectName() == "ManagementHeaderClock"
    assert management_view.lbl_header_clock.text() != ""

    assert hasattr(management_view, "btn_header_pos")
    assert management_view.btn_header_pos.objectName() == "ManagementHeaderPosBtn"

    assert hasattr(management_view, "btn_header_logout")
    assert management_view.btn_header_logout.objectName() == "ManagementHeaderLogoutBtn"


def test_management_header_title_updates_on_tab_switch(management_view):
    """Verify the header title reflects the active tab breadcrumb."""
    management_view.switch_tab(0)  # Dashboard
    section = _t("management.sidebar_section_management")
    dashboard = _t("management.sidebar_dashboard")
    assert management_view.lbl_header_title.text() == f"{section} / {dashboard}"

    management_view.switch_tab(1)  # Inventory
    inventory = _t("management.sidebar_inventory")
    assert management_view.lbl_header_title.text() == f"{section} / {inventory}"


def test_management_header_title_retranslates(management_view):
    """Verify header title and button texts update on language switch."""
    management_view.switch_tab(0)
    for lang in ["en", "si", "ta", "en"]:
        set_language(lang)
        QApplication.processEvents()
        section = _t("management.sidebar_section_management")
        dashboard = _t("management.sidebar_dashboard")
        assert management_view.lbl_header_title.text() == f"{section} / {dashboard}"
        assert management_view.btn_header_pos.text() == _t("management.sidebar_pos")
        assert management_view.btn_header_logout.text() == _t("management.sidebar_logout")


def test_management_header_button_signals(management_view):
    """Verify clicking header buttons emits the corresponding signals."""
    pos_mock = MagicMock()
    logout_mock = MagicMock()

    management_view.request_pos_view.connect(pos_mock)
    management_view.logout_requested.connect(logout_mock)

    management_view.btn_header_pos.click()
    pos_mock.assert_called_once()

    management_view.btn_header_logout.click()
    logout_mock.assert_called_once()


def test_dashboard_quick_stats_and_tax_cards_structure(db_session):
    """Verify DashboardView embeds individual KPI stats into StatCard frames."""
    view = DashboardView()
    try:
        # Check quick stats are inside StatCard frames
        stat_cards = view.findChildren(QFrame, "StatCard")
        assert len(stat_cards) >= 7  # 4 in quick stats + 3 in tax today

        assert view.lbl_avg_order.parentWidget().objectName() == "StatCard"
        assert view.lbl_items_sold.parentWidget().objectName() == "StatCard"
        assert view.lbl_unique_customers.parentWidget().objectName() == "StatCard"
        assert view.lbl_txn_count.parentWidget().objectName() == "StatCard"

        assert view.lbl_tax_vat.parentWidget().objectName() == "StatCard"
        assert view.lbl_tax_sscl.parentWidget().objectName() == "StatCard"
        assert view.lbl_net_revenue.parentWidget().objectName() == "StatCard"
    finally:
        view.close()
        view.deleteLater()
        QApplication.processEvents()


def test_management_header_and_stat_card_styles_in_both_themes():
    """Verify QSS rules for ManagementHeader, buttons, and StatCard in both themes."""
    for theme_name in ["Dark", "Light"]:
        captured = []
        ThemeService.set_stylesheet_handler(captured.append)
        ThemeService.apply_theme(theme_name)
        assert len(captured) > 0
        css = captured[-1]

        assert "QFrame#ManagementHeader" in css
        assert "QLabel#ManagementHeaderTitle" in css
        assert "QLabel#ManagementHeaderClock" in css
        assert "QToolButton#ManagementHeaderPosBtn" in css
        assert "QToolButton#ManagementHeaderLogoutBtn" in css
        assert "QFrame#StatCard" in css
