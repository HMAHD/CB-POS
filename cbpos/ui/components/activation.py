"""View lifecycle: reload a cached view's data each time it is shown.

Management views are created once and kept for the session, so a view that
loads only in ``__init__`` shows stale data until the user presses Refresh.
A view that mixes in :class:`Activatable` gets :meth:`on_activated` every
time it becomes the visible page; containers call :func:`activate`.
"""

from PyQt6.QtWidgets import QStackedWidget, QTabWidget, QWidget


class Activatable:
    """Mixin for views that must refresh their data when shown again."""

    def on_activated(self) -> None:
        """Called every time this view becomes the visible page. Reload data here; keep it cheap."""


def activate(widget: QWidget | None) -> None:
    """Tell *widget* it is now visible, if it takes part in the view lifecycle."""
    if isinstance(widget, Activatable):
        widget.on_activated()


def activate_current_tab(tabs: QTabWidget | QStackedWidget) -> None:
    """Forward activation to the page a tab or stack container is showing."""
    activate(tabs.currentWidget())


def forward_tab_activation(tabs: QTabWidget) -> None:
    """Activate each tab page when the user switches to it."""
    tabs.currentChanged.connect(lambda _index: activate_current_tab(tabs))
