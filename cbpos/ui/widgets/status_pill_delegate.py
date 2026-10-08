"""Status shown as a rounded, theme-aware pill inside a table cell (#560).

Coloured status *text* lost its colour on the selected row (the QSS
selection colour wins) and relied on colour alone. A pill carries the
status by shape and text too, and paints its own opaque fill, so it reads
the same on plain, alternate and selected rows.

Usage::

    table.setItemDelegateForColumn(STATUS_COL, StatusPillDelegate(table))
    set_status_pill(item, display_text, SUCCESS)

The cell keeps its text as the item's DisplayRole -- the pill shows
whatever display string it is given (a raw code today, a translated label
once #582 lands) -- and the palette meaning in ``STATUS_MEANING_ROLE``.
Cells without a meaning paint as ordinary text.
"""

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableWidgetItem

from cbpos.ui.resources.status_colors import pill_colors

STATUS_MEANING_ROLE = Qt.ItemDataRole.UserRole + 50

_PAD_X = 10
_PAD_Y = 2
_MARGIN = 6


def set_status_pill(item: QTableWidgetItem, text: str, meaning: str | None) -> QTableWidgetItem:
    """Give ``item`` its status text and palette meaning (success/danger/warning/info/neutral)."""
    item.setText(text)
    item.setData(STATUS_MEANING_ROLE, meaning)
    return item


class StatusPillDelegate(QStyledItemDelegate):
    """Paints a cell's text as a rounded pill coloured by its palette meaning."""

    @staticmethod
    def _font(option: QStyleOptionViewItem) -> QFont:
        font = QFont(option.font)
        font.setBold(True)
        return font

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Draw the row background/selection, then the pill on top."""
        meaning = index.data(STATUS_MEANING_ROLE)
        if not meaning:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""  # background and selection only
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        font = self._font(opt)
        metrics = QFontMetrics(font)
        height = min(metrics.height() + 2 * _PAD_Y, opt.rect.height() - 2)
        width = min(metrics.horizontalAdvance(text) + 2 * _PAD_X, opt.rect.width() - 2 * _MARGIN)
        pill = QRect(opt.rect.left() + _MARGIN, 0, max(width, 0), height)
        pill.moveTop(opt.rect.top() + (opt.rect.height() - height) // 2)

        fg, fill = pill_colors(meaning)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(pill, height / 2, height / 2)
        painter.setPen(fg)
        painter.setFont(font)
        # Elide only when the text really can't fit: elidedText() at exactly
        # the text's own advance elides it (rounding), clipping "COMPLETED".
        room = pill.width() - 2 * _PAD_X
        if metrics.horizontalAdvance(text) > room:
            text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(room, 0))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Wide enough for the pill plus its margins, so ResizeToContents fits it."""
        hint = super().sizeHint(option, index)
        if not index.data(STATUS_MEANING_ROLE):
            return hint
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)  # the font paint() will use
        metrics = QFontMetrics(self._font(opt))
        width = metrics.horizontalAdvance(opt.text) + 2 * (_PAD_X + _MARGIN) + 2
        return QSize(max(hint.width(), width), hint.height())
