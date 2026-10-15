"""
#611: a trailing stretch inside FilterWidget pushed Run Report to the far
right of the filter bar, away from the filters it applies; and the
Print / Excel / PDF / Email buttons were squeezed below their labels'
width on narrow windows (1024 px, or larger text, or long Tamil labels).
"""

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget

from cbpos.core.reports import register_all_reports
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import get_language, set_language
from cbpos.ui.views.reports.report_viewer import ReportViewer

MANAGEMENT_SIDEBAR_WIDTH = 250  # CollapsibleSidebar's expanded width, left of Reports


@pytest.fixture
def reports_screen(qapp, db_session, monkeypatch):
    """Build the themed Reports screen inside a window of the given size and language."""
    original_language = get_language()
    monkeypatch.setattr(ThemeService, "current_theme", ThemeService.current_theme)
    captured: list[str] = []
    monkeypatch.setattr(ThemeService, "_set_stylesheet", captured.append)
    ConfigService.get("font_size")  # make sure settings are loaded
    register_all_reports()
    windows: list[QWidget] = []

    def _build(width: int, height: int, lang: str, font_size: int = 12) -> ReportViewer:
        set_language(lang)
        monkeypatch.setitem(ConfigService._settings, "font_size", font_size)
        ThemeService.apply_theme("Dark")

        window = QWidget()
        # The real QSS (paddings, min-widths, font sizes) decides the widths,
        # scoped to this window rather than the whole test app.
        window.setStyleSheet(captured[-1])
        layout = QHBoxLayout(window)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        management_sidebar = QWidget()
        management_sidebar.setFixedWidth(MANAGEMENT_SIDEBAR_WIDTH)
        layout.addWidget(management_sidebar)
        viewer = ReportViewer()
        layout.addWidget(viewer, 1)
        window.resize(width, height)
        window.show()
        windows.append(window)
        QApplication.processEvents()
        return viewer

    yield _build
    for window in windows:
        window.close()
        window.deleteLater()
    set_language(original_language)


def _open_report(viewer: ReportViewer, report_id: str) -> None:
    next(b for b in viewer.findChildren(QPushButton, "ReportNavItem") if b.property("report_id") == report_id).click()
    QApplication.processEvents()


def _left(widget: QWidget, viewer: ReportViewer) -> int:
    return widget.mapTo(viewer, QPoint(0, 0)).x()


def _right(widget: QWidget, viewer: ReportViewer) -> int:
    return widget.mapTo(viewer, QPoint(widget.width(), 0)).x()


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_run_report_sits_right_after_the_filters(reports_screen, lang):
    viewer = reports_screen(1366, 768, lang)
    _open_report(viewer, "daily_sales_summary")

    last_filter = viewer.filter_widget.inputs["date_range"]["end"]
    gap = _left(viewer.btn_run, viewer) - _right(last_filter, viewer)

    assert 0 <= gap <= 24
