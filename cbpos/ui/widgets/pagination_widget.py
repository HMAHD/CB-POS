"""
Reusable pagination widget for large data tables.

Provides Previous/Next navigation, a "Showing X-Y of Z" indicator,
and a signal when the page changes so the parent view can update its table.
"""

import weakref
from typing import TypeVar

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from cbpos.i18n import _t, register_language_callback, unregister_language_callback

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50


class PaginationWidget(QWidget):
    """A pagination bar that slices a list of items into pages.

    Signals:
        page_changed(int): Emitted with the new page number (0-based).
    """

    page_changed = pyqtSignal(int)

    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE, parent: QWidget | None = None) -> None:
        """Create the pagination bar at page 0 with no items yet.

        Args:
            page_size: Number of items shown per page.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._page_size = page_size
        self._total_items = 0
        self._current_page = 0
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        self._info_label = QLabel()
        self._info_label.setProperty("class", "muted")
        layout.addWidget(self._info_label)

        layout.addStretch()

        self._btn_prev = QPushButton(_t("common.previous"))
        self._btn_prev.setFixedWidth(90)
        self._btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_prev.clicked.connect(self._go_prev)
        layout.addWidget(self._btn_prev)

        self._page_label = QLabel()
        layout.addWidget(self._page_label)

        self._btn_next = QPushButton(_t("common.next"))
        self._btn_next.setFixedWidth(90)
        self._btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_next.clicked.connect(self._go_next)
        layout.addWidget(self._btn_next)

        self._update_controls()
        register_language_callback(self._retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        def _unregister():
            widget = self_ref()
            if widget is not None:
                unregister_language_callback(widget._retranslate_ui)

        self.destroyed.connect(_unregister)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_total(self, total: int) -> None:
        """Update the total item count and reset to page 0."""
        self._total_items = total
        self._current_page = 0
        self._update_controls()

    def get_page_slice(self, items: list) -> list:
        """Return the slice of *items* for the current page."""
        start = self._current_page * self._page_size
        end = start + self._page_size
        return items[start:end]

    @property
    def page_size(self) -> int:
        """Number of items shown per page."""
        return self._page_size

    @property
    def current_page(self) -> int:
        """Current page index (0-based)."""
        return self._current_page

    @property
    def total_pages(self) -> int:
        """Total number of pages, at least 1."""
        if self._total_items == 0:
            return 1
        return (self._total_items + self._page_size - 1) // self._page_size

    @property
    def start_index(self) -> int:
        """Index of the first item on the current page."""
        return self._current_page * self._page_size

    @property
    def end_index(self) -> int:
        """Index one past the last item on the current page, clamped to the total."""
        return min(self.start_index + self._page_size, self._total_items)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_prev(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._update_controls()
            self.page_changed.emit(self._current_page)

    def _go_next(self) -> None:
        if self._current_page < self.total_pages - 1:
            self._current_page += 1
            self._update_controls()
            self.page_changed.emit(self._current_page)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_controls(self) -> None:
        total = self._total_items
        if total == 0:
            self._info_label.setText(_t("common.no_items"))
            self._page_label.setText("")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            self.setVisible(False)
            return

        # A disabled-looking-but-not-disabled Previous/Next pair with
        # "Page 1 of 1" is noise when there's nothing to actually page
        # through -- hide the whole control, not just its buttons (#291).
        self.setVisible(self.total_pages > 1)
        start = self.start_index + 1
        end = self.end_index
        self._info_label.setText(_t("common.showing_range", start=start, end=end, total=total))
        self._page_label.setText(_t("common.page_of", page=self._current_page + 1, total=self.total_pages))
        self._btn_prev.setText(_t("common.previous"))
        self._btn_next.setText(_t("common.next"))
        self._btn_prev.setEnabled(self._current_page > 0)
        self._btn_next.setEnabled(self._current_page < self.total_pages - 1)

    def _retranslate_ui(self) -> None:
        """Update button text when language changes."""
        self._update_controls()
