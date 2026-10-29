"""Theme callbacks must not outlive the widget that registered them.

ThemeService.theme_change_callbacks is process-global; a widget that registers
a bound method and is then deleted left the callback behind, so every later
theme change logged "wrapped C/C++ object ... has been deleted" and the list
grew by one entry per dialog opened.
"""

import logging

from PyQt6.QtCore import QCoreApplication, QEvent

from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget
from cbpos.ui.widgets.page_header import PageHeader


def _delete_now(widget) -> None:
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def test_deleted_widgets_leave_no_theme_callbacks(app_fixture, monkeypatch, caplog):
    monkeypatch.setattr(ThemeService, "_set_stylesheet", lambda css: None)
    widgets = [EmptyStateWidget(Icons.INVENTORY), PageHeader(Icons.INVENTORY, "Title")]
    owner_ids = {id(w) for w in widgets}
    for widget in widgets:
        _delete_now(widget)
    del widgets, widget

    with caplog.at_level(logging.ERROR, logger="cbpos.core.services.theme_service"):
        ThemeService.apply_theme("Dark")

    leftover = [cb for cb in ThemeService.theme_change_callbacks if id(getattr(cb, "__self__", None)) in owner_ids]
    assert leftover == []
    assert "has been deleted" not in caplog.text
