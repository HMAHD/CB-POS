"""
Reusable pagination widget for large data tables.

Provides Previous/Next navigation, a "Showing X-Y of Z" indicator,
and a signal when the page changes so the parent view can update its table.
"""

from typing import TypeVar

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal
from cbpos.i18n import _t

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50


class PaginationWidget(QWidget):
    """A pagination bar that slices a list of items into pages.

    Signals:
        page_changed(int): Emitted with the new page number (0-based).
    """

    page_changed = pyqtSignal(int)

    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE, parent: QWidget | None = None) -> None:
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
        return self._page_size

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def total_pages(self) -> int:
        if self._total_items == 0:
            return 1
        return (self._total_items + self._page_size - 1) // self._page_size

    @property
    def start_index(self) -> int:
        return self._current_page * self._page_size

    @property
    def end_index(self) -> int:
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

        self.setVisible(True)
        start = self.start_index + 1
        end = self.end_index
        self._info_label.setText(_t("common.showing_range", start=start, end=end, total=total))
        self._page_label.setText(_t("common.page_of", page=self._current_page + 1, total=self.total_pages))
        self._btn_prev.setEnabled(self._current_page > 0)
        self._btn_next.setEnabled(self._current_page < self.total_pages - 1)
