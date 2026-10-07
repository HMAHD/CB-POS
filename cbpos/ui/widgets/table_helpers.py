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

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

# Cells and headers of number columns share this, so a header sits over
# the right edge of its digits instead of centered above them (#554).
NUMERIC_ALIGNMENT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


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


def align_numeric_headers(table: QTableWidget, columns: Iterable[int]) -> None:
    """Right-align the horizontal header of each numeric column.

    QSS cannot target one header section, so alignment goes on the header
    item. Call after `setHorizontalHeaderLabels()`; Qt reuses the items on
    later relabels, so retranslation keeps the alignment.

    Args:
        table: the table whose header to align.
        columns: indexes of columns whose cells are right-aligned numbers.
    """
    for column in columns:
        item = table.horizontalHeaderItem(column)
        if item is None:
            item = QTableWidgetItem()
            table.setHorizontalHeaderItem(column, item)
        item.setTextAlignment(NUMERIC_ALIGNMENT)
