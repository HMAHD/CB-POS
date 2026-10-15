"""A layout that lays widgets out in a row and wraps onto more rows when narrow."""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    """Row of widgets that wraps onto more rows instead of squeezing them.

    Each widget always gets its full size hint, so a button never shrinks
    below its label. When the row doesn't fit, the remaining widgets move
    to a new row, and the layout reports the taller height via
    ``heightForWidth`` so the parent makes room (#611). Rows hug the left
    edge by default, or the right edge with ``align_right=True``.
    """

    def __init__(self, parent: QWidget | None = None, spacing: int = 8, align_right: bool = False) -> None:
        """Create the layout with the given gap between widgets and between rows."""
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._align_right = align_right
        self.setSpacing(spacing)

    # -- QLayout item bookkeeping ------------------------------------

    def addItem(self, item: QLayoutItem) -> None:
        """Append an item (called by addWidget)."""
        self._items.append(item)

    def count(self) -> int:
        """Number of items in the layout."""
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        """Item at index, or None."""
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        """Remove and return the item at index, or None."""
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    # -- Sizing --------------------------------------------------------

    def expandingDirections(self) -> Qt.Orientation:
        """Never ask for more space than the widgets need."""
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        """Height depends on how many rows the width allows."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Height needed to show every widget at this width."""
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def sizeHint(self) -> QSize:
        """Everything on a single row."""
        items = self._visible_items()
        width = sum(i.sizeHint().width() for i in items) + self.spacing() * max(len(items) - 1, 0)
        height = max((i.sizeHint().height() for i in items), default=0)
        return self._with_margins(QSize(width, height))

    def minimumSize(self) -> QSize:
        """The widest single widget: narrower than that would clip it."""
        size = QSize()
        for item in self._visible_items():
            size = size.expandedTo(item.sizeHint())
        return self._with_margins(size)

    def setGeometry(self, rect: QRect) -> None:
        """Place the widgets inside rect."""
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    # -- Internals -----------------------------------------------------

    def _visible_items(self) -> list[QLayoutItem]:
        return [i for i in self._items if i.widget() is None or not i.widget().isHidden()]

    def _with_margins(self, size: QSize) -> QSize:
        m = self.contentsMargins()
        return QSize(size.width() + m.left() + m.right(), size.height() + m.top() + m.bottom())

    def _do_layout(self, rect: QRect, apply: bool) -> int:
        """Split the widgets into rows that fit rect's width, and place them if apply.

        Returns the total height used, margins included.
        """
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        gap = self.spacing()

        rows: list[list[QLayoutItem]] = []
        row_width = 0
        for item in self._visible_items():
            w = item.sizeHint().width()
            if rows and rows[-1] and row_width + gap + w <= area.width():
                rows[-1].append(item)
                row_width += gap + w
            else:
                rows.append([item])
                row_width = w

        y = area.y()
        for index, row in enumerate(rows):
            if index:
                y += gap
            row_height = max(i.sizeHint().height() for i in row)
            width = sum(i.sizeHint().width() for i in row) + gap * (len(row) - 1)
            x = area.x() + (max(area.width() - width, 0) if self._align_right else 0)
            for item in row:
                hint = item.sizeHint()
                if apply:
                    item.setGeometry(QRect(QPoint(x, y + (row_height - hint.height()) // 2), hint))
                x += hint.width() + gap
            y += row_height
        return y - rect.y() + m.bottom()
