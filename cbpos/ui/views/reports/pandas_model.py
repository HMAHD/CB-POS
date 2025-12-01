from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
import pandas as pd


class PandasModel(QAbstractTableModel):
    """
    A model to interface a Qt view with pandas dataframe.
    """

    def __init__(self, data: pd.DataFrame = pd.DataFrame()):
        super().__init__()
        self._data = data

    def rowCount(self, parent=QModelIndex()):
        return self._data.shape[0]

    def columnCount(self, parent=QModelIndex()):
        return self._data.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]

            # Format floats/decimals
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                if isinstance(value, float):
                    return "{:.2f}".format(value)
                return str(value)

            return str(value)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            value = self._data.iloc[index.row(), index.column()]
            if isinstance(value, (int, float)):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        return None

    def headerData(self, col, orientation, role):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return str(self._data.columns[col])
        return None

    def set_data(self, data: pd.DataFrame):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def get_dataframe(self) -> pd.DataFrame:
        return self._data
