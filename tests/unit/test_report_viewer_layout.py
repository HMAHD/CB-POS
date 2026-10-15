"""
#611: a trailing stretch inside FilterWidget pushed Run Report to the far
right of the filter bar, away from the filters it applies; and the
Print / Excel / PDF / Email buttons were squeezed below their labels'
width on narrow windows (1024 px, or larger text, or long Tamil labels).
"""

import pandas as pd
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
def reports_screen(app_fixture, db_session, monkeypatch):
    """Build the themed Reports screen inside a window of the given size and language.

    app_fixture loads the app's bundled fonts (Noto Sans / Sinhala / Tamil),
    which decide how wide each label really is.
    """
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


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_filters_and_run_report_fit_a_1024_window_unsqueezed(reports_screen, lang):
    viewer = reports_screen(1024, 768, lang)
    _open_report(viewer, "daily_sales_summary")

    misfits = [
        w.objectName()
        for w in (viewer.filter_widget, viewer.btn_run)
        if w.width() < w.sizeHint().width() or w.mapTo(viewer.window(), QPoint(w.width(), 0)).x() > 1024
    ]
    assert misfits == []


def _run_report_with_rows(viewer: ReportViewer, qtbot, monkeypatch) -> None:
    """Open a report and run it, with the report returning a page of rows."""
    _open_report(viewer, "daily_sales_summary")
    rows = pd.DataFrame({"Date": ["2026-10-01"] * 3, "Total Sales": [1250.0, 980.5, 40.0]})
    monkeypatch.setattr(viewer.current_report, "generate", lambda _filters: rows)
    viewer.btn_run.click()
    qtbot.waitUntil(viewer.action_bar.isVisible, timeout=3000)
    QApplication.processEvents()


# 1366x768 is the common shop laptop; 1024 px is the issue's narrow window;
# font size 20 is a large-text user.
@pytest.mark.parametrize(("width", "font_size"), [(1366, 12), (1366, 20), (1024, 12)])
@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_export_buttons_show_their_whole_label(reports_screen, qtbot, monkeypatch, width, font_size, lang):
    viewer = reports_screen(width, 768, lang, font_size)
    _run_report_with_rows(viewer, qtbot, monkeypatch)

    squeezed = [
        btn.text()
        for btn in (viewer.btn_print, viewer.btn_export_excel, viewer.btn_export_pdf, viewer.btn_email)
        if btn.width() < btn.sizeHint().width()
        # The screen is `width` wide; a screen minimum wider than that
        # (e.g. from the filter bar) pushes the buttons off its right edge.
        or btn.mapTo(viewer.window(), QPoint(btn.width(), 0)).x() > width
        or btn.mapTo(viewer.action_bar, QPoint(0, btn.height())).y() > viewer.action_bar.height()
    ]
    assert squeezed == []
