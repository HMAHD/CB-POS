"""Shared helpers for configuring table/tree column sizing correctly.

Nearly every table in the app had the same defect, arrived at two
different ways:

1. A resize mode set once with no column index (the single-arg
   `setSectionResizeMode(mode)` overload), applying the same rule to
   every column regardless of content -- so a short column (STATUS, an
   ID) stretches to fill space while a long one (a name, a description)
   gets Qt's default `Interactive` width and truncates.
2. `setStretchLastSection(True)` (Qt's own default) forcing whichever
   column happens to be *last* to absorb all extra space, independent
   of whether that's actually the column that needs it.

`configure_table_columns()` makes the correct pattern -- an explicit,
deliberate mode per column, with `stretchLastSection` off unless asked
for -- the easy, obvious thing to reach for instead.
"""

from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date, datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QTableView, QTableWidget, QTableWidgetItem

from cbpos.core.utils.formatters import format_datetime, format_relative_time
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget
from cbpos.ui.widgets.status_pill_delegate import (
    STATUS_MEANING_ROLE,
    StatusPillDelegate,
    set_status_pill,
)

# Cells and headers of number columns share this, so a header sits over
# the right edge of its digits instead of centered above them (#554).
NUMERIC_ALIGNMENT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


@contextmanager
def batch_table_update(table: QTableWidget | QTableView):
    """Context manager for batch row updates on QTableWidget or QTableView.

    Disables updates and sorting during bulk insertions to avoid intermediate
    repaints and redundant sorting, restoring prior states on exit.
    Refreshes attached EmptyStateWidget if present.
    """
    was_updates = table.updatesEnabled()
    was_sorting = table.isSortingEnabled() if hasattr(table, "isSortingEnabled") else False
    table.setUpdatesEnabled(False)
    if hasattr(table, "setSortingEnabled") and was_sorting:
        table.setSortingEnabled(False)
    try:
        yield table
    finally:
        if hasattr(table, "setSortingEnabled") and was_sorting:
            table.setSortingEnabled(True)
        table.setUpdatesEnabled(was_updates)
        if hasattr(table, "update_empty_state") and callable(table.update_empty_state):
            try:
                table.update_empty_state()
            except Exception:
                pass


def attach_table_empty_state(
    table: QTableView,
    icon_name: str,
    title_key: str | None = None,
    subtitle_key: str | None = None,
) -> EmptyStateWidget:
    """Attach an EmptyStateWidget overlay to a table's viewport.

    The overlay resizes automatically with the viewport and updates visibility
    when rows are added or cleared in the table's model, keeping horizontal
    headers visible.

    Args:
        table: QTableView or QTableWidget to attach the empty state to.
        icon_name: qtawesome icon name (e.g. Icons.INVENTORY).
        title_key: Optional translation key (or plain text) for the headline.
        subtitle_key: Optional translation key (or plain text) for subtitle.

    Returns:
        The created EmptyStateWidget instance.
    """
    empty_widget = EmptyStateWidget(icon_name, parent=table.viewport())

    def _retranslate() -> None:
        try:
            if title_key:
                empty_widget.set_title(_t(title_key))
            if subtitle_key:
                empty_widget.set_subtitle(_t(subtitle_key))
        except (RuntimeError, AttributeError):
            pass

    _retranslate()
    register_language_callback(_retranslate, owner=empty_widget)

    def _cleanup() -> None:
        try:
            unregister_language_callback(_retranslate)
        except Exception:
            pass

    try:
        table.destroyed.connect(_cleanup)
    except (RuntimeError, AttributeError):
        pass

    def update_visibility(*_args) -> None:
        try:
            model = table.model()
            is_empty = (model.rowCount() == 0) if model is not None else True
            empty_widget.setVisible(is_empty)
        except (RuntimeError, AttributeError):
            pass

    def _connect_model(model) -> None:
        if model is None:
            return
        try:
            model.rowsInserted.connect(update_visibility)
            model.rowsRemoved.connect(update_visibility)
            model.modelReset.connect(update_visibility)
            model.layoutChanged.connect(update_visibility)
        except (AttributeError, RuntimeError):
            pass

    try:
        _connect_model(table.model())
    except (RuntimeError, AttributeError):
        pass

    try:
        orig_set_model = table.setModel

        def _wrapped_set_model(m):
            orig_set_model(m)
            _connect_model(m)
            update_visibility()

        table.setModel = _wrapped_set_model
    except (RuntimeError, AttributeError):
        pass

    table._empty_state = empty_widget
    table.empty_state_widget = empty_widget
    table.update_empty_state = update_visibility

    update_visibility()
    return empty_widget


def configure_table_columns(
    header: QHeaderView,
    column_modes: dict[int, QHeaderView.ResizeMode],
    stretch_last_section: bool = False,
    minimum_section_size: int | None = None,
) -> None:
    """Apply an explicit resize mode to every listed column.

    Args:
        header: the table/tree's horizontal header (e.g. `table.horizontalHeader()`).
        column_modes: `{column_index: ResizeMode}` for every column that needs
            an explicit mode. Any column not listed keeps Qt's default
            (`Interactive`) -- list every real column to avoid surprises.
        stretch_last_section: Qt defaults this to True, which silently makes
            the last column compete for space regardless of `column_modes`.
            Left off by default here since that default is the root cause
            of half of this bug's instances.
        minimum_section_size: if given, floors every column's width so a
            `ResizeToContents` column that starts out empty (e.g. a live-typed
            value column with no data yet) can't collapse to near-nothing.
    """
    header.setStretchLastSection(stretch_last_section)
    if minimum_section_size is not None:
        header.setMinimumSectionSize(minimum_section_size)
    for column, mode in column_modes.items():
        header.setSectionResizeMode(column, mode)


def align_numeric_headers(table: QTableView, columns: Iterable[int]) -> None:
    """Right-align the horizontal header of each numeric column.

    QSS cannot target one header section, so alignment goes on the header
    item. Call after `setHorizontalHeaderLabels()`; Qt reuses the items on
    later relabels, so retranslation keeps the alignment.

    Args:
        table: the table whose header to align (QTableWidget or QTableView).
        columns: indexes of columns whose cells are right-aligned numbers.
    """
    for column in columns:
        if hasattr(table, "horizontalHeaderItem"):
            item = table.horizontalHeaderItem(column)
            if item is None:
                item = QTableWidgetItem()
                table.setHorizontalHeaderItem(column, item)
            item.setTextAlignment(NUMERIC_ALIGNMENT)
        elif hasattr(table, "model"):
            try:
                model = table.model()
                if model is not None:
                    if hasattr(model, "horizontalHeaderItem"):
                        item = model.horizontalHeaderItem(column)
                        if item is not None:
                            item.setTextAlignment(NUMERIC_ALIGNMENT)
                    elif hasattr(model, "setHeaderData"):
                        model.setHeaderData(
                            column,
                            Qt.Orientation.Horizontal,
                            NUMERIC_ALIGNMENT,
                            Qt.ItemDataRole.TextAlignmentRole,
                        )
            except (RuntimeError, AttributeError):
                pass


class RelativeTimeTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem displaying humanized relative time while preserving exact datetime sorting and tooltip (#774).

    Displays relative time (e.g. "Just now", "5 minutes ago", "2 days ago") as the cell text,
    stores the exact timestamp as a tooltip, and enables chronological sorting via __lt__ on
    the underlying parsed datetime.
    """

    def __init__(
        self,
        dt_or_str: datetime | date | str | None,
        fmt: str = "%Y-%m-%d %H:%M",
        now: datetime | None = None,
    ) -> None:
        self._raw_dt = self._parse_dt(dt_or_str)
        rel_text = format_relative_time(dt_or_str, now=now) if dt_or_str else ""
        super().__init__(rel_text)
        if self._raw_dt:
            exact_str = format_datetime(self._raw_dt) if fmt == "%Y-%m-%d %H:%M" else self._raw_dt.strftime(fmt)
            self.setToolTip(exact_str)
            self.setData(Qt.ItemDataRole.UserRole, self._raw_dt.timestamp())

    @staticmethod
    def _parse_dt(dt_or_str: datetime | date | str | None) -> datetime | None:
        if not dt_or_str:
            return None
        if isinstance(dt_or_str, datetime):
            return dt_or_str
        if isinstance(dt_or_str, date):
            return datetime.combine(dt_or_str, datetime.min.time())
        if isinstance(dt_or_str, str):
            clean = dt_or_str.strip().replace(",", ".")
            try:
                return datetime.fromisoformat(clean)
            except ValueError:
                for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(clean.split(".")[0], f)
                    except ValueError:
                        pass
        return None

    def __lt__(self, other: object) -> bool:
        if isinstance(other, RelativeTimeTableWidgetItem):
            if self._raw_dt is not None and other._raw_dt is not None:
                return self._raw_dt < other._raw_dt
            if self._raw_dt is not None:
                return False
            if other._raw_dt is not None:
                return True
        if isinstance(other, QTableWidgetItem):
            val1 = self.data(Qt.ItemDataRole.UserRole)
            val2 = other.data(Qt.ItemDataRole.UserRole)
            if val1 is not None and val2 is not None:
                try:
                    return val1 < val2
                except TypeError:
                    pass
        return super().__lt__(other)


__all__ = [
    "NUMERIC_ALIGNMENT",
    "STATUS_MEANING_ROLE",
    "RelativeTimeTableWidgetItem",
    "StatusPillDelegate",
    "align_numeric_headers",
    "attach_table_empty_state",
    "batch_table_update",
    "configure_table_columns",
    "set_status_pill",
]
