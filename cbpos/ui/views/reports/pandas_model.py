"""Qt table model that adapts a pandas DataFrame for display in a QTableView."""

from typing import Any

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor, QFont

from cbpos.core.services.theme_service import ThemeService
from cbpos.core.utils.formatters import format_currency

RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
LEFT_ALIGNED = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def _is_numeric(value: Any) -> bool:
    """True for a value whose cell renders right-aligned."""
    return isinstance(value, (int, float))


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
        """Initialize the model with a DataFrame and optional render hints."""
        super().__init__()
        self._data = data if data is not None else pd.DataFrame()
        self._hints = render_hints or {}
        self._numeric_columns = self._find_numeric_columns()

    def rowCount(self, parent=QModelIndex()):
        """Return the number of rows in the underlying DataFrame."""
        return self._data.shape[0]

    def columnCount(self, parent=QModelIndex()):
        """Return the number of columns in the underlying DataFrame."""
        return self._data.shape[1]

    def _find_numeric_columns(self) -> set[int]:
        """Columns whose every cell is right-aligned, so the header can match (#554)."""
        if self._data.empty:
            return set()
        return {
            col
            for col in range(self._data.shape[1])
            # to_numpy() yields the same scalars as iloc[row, col] in data();
            # tolist() would turn np.int64 into int and disagree with the cells.
            if all(_is_numeric(value) for value in self._data.iloc[:, col].to_numpy())
        }

    def _is_total_row(self, row: int) -> bool:
        total_col = self._hints.get("total_row_column")
        total_values = self._hints.get("total_row_values")
        if not total_col or not total_values or total_col not in self._data.columns:
            return False
        return self._data.iloc[row][total_col] in total_values

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return the display value, alignment, font, or color for a cell based on role and render hints."""
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
            return RIGHT_ALIGNED if _is_numeric(value) else LEFT_ALIGNED

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
        """Return the column name, right-aligned over all-numeric columns; None for vertical headers."""
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self._data.columns[col])
        if role == Qt.ItemDataRole.TextAlignmentRole and col in self._numeric_columns:
            return RIGHT_ALIGNED
        return None

    def set_data(self, data: pd.DataFrame, render_hints: dict[str, Any] | None = None):
        """Replace the underlying DataFrame and render hints, resetting the model."""
        self.beginResetModel()
        self._data = data
        self._hints = render_hints or {}
        self._numeric_columns = self._find_numeric_columns()
        self.endResetModel()

    def get_dataframe(self) -> pd.DataFrame:
        """Return the underlying DataFrame."""
        return self._data
