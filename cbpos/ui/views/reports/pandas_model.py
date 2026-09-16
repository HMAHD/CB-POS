from typing import Any

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor, QFont

from cbpos.core.services.theme_service import ThemeService
from cbpos.core.utils.formatters import format_currency


class PandasModel(QAbstractTableModel):
    """
    A model to interface a Qt view with pandas dataframe.

    ``render_hints`` lets a report mark up its own data without every
    report type sharing identical, generic styling (#290): which
    columns hold money (formatted via the app's currency formatter
    instead of raw "{:.2f}"), which column/row marks the grand total
    (bold + tinted), and which column carries a directional tag (e.g.
    Inflow/Outflow) mapped to a text color. All keys are optional --
    omitting a key (or the whole dict) renders exactly as before.

    Supported keys:
        currency_columns (list[str]): column names formatted as currency.
        total_row_column (str): column name whose value identifies a total row.
        total_row_values (list[str]): values in that column marking a total row.
        color_column (str): column name carrying a directional tag.
        color_map (dict[str, str]): tag value -> hex color string.
    """

    def __init__(self, data: pd.DataFrame = None, render_hints: dict[str, Any] | None = None):
        super().__init__()
        self._data = data if data is not None else pd.DataFrame()
        self._hints = render_hints or {}

    def rowCount(self, parent=QModelIndex()):
        return self._data.shape[0]

    def columnCount(self, parent=QModelIndex()):
        return self._data.shape[1]

    def _is_total_row(self, row: int) -> bool:
        total_col = self._hints.get("total_row_column")
        total_values = self._hints.get("total_row_values")
        if not total_col or not total_values or total_col not in self._data.columns:
            return False
        return self._data.iloc[row][total_col] in total_values

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row, col = index.row(), index.column()
        value = self._data.iloc[row, col]
        column_name = self._data.columns[col]

        if role == Qt.ItemDataRole.DisplayRole:
            currency_columns = self._hints.get("currency_columns") or []
            if column_name in currency_columns:
                return format_currency(value)

            if isinstance(value, (float, int)) and not isinstance(value, bool):
                if isinstance(value, float):
                    return f"{value:.2f}"
                return str(value)

            return str(value)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if isinstance(value, (int, float)):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        elif role == Qt.ItemDataRole.FontRole:
            if self._is_total_row(row):
                font = QFont()
                font.setBold(True)
                return font
            return None

        elif role == Qt.ItemDataRole.BackgroundRole:
            if self._is_total_row(row):
                accent = QColor(ThemeService.get_accent_color())
                accent.setAlpha(35)
                return accent
            return None

        elif role == Qt.ItemDataRole.ForegroundRole:
            color_column = self._hints.get("color_column")
            color_map = self._hints.get("color_map") or {}
            if color_column and column_name == color_column:
                row_tag = self._data.iloc[row][color_column]
                hex_color = color_map.get(row_tag)
                if hex_color:
                    return QColor(hex_color)
            return None

        return None

    def headerData(self, col, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return str(self._data.columns[col])
        return None

    def set_data(self, data: pd.DataFrame, render_hints: dict[str, Any] | None = None):
        self.beginResetModel()
        self._data = data
        self._hints = render_hints or {}
        self.endResetModel()

    def get_dataframe(self) -> pd.DataFrame:
        return self._data
