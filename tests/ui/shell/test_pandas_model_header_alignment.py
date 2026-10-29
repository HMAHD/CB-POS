"""#554: Reports headers right-align over columns whose cells right-align.

PandasModel right-aligned numeric cells but left every header centered,
so amount columns looked offset from their own titles.
"""

from decimal import Decimal

import pandas as pd
import pytest
from PyQt6.QtCore import Qt

from cbpos.ui.views.reports.pandas_model import PandasModel

pytestmark = pytest.mark.usefixtures("qapp")

H = Qt.Orientation.Horizontal
ALIGN = Qt.ItemDataRole.TextAlignmentRole


def _is_right(alignment) -> bool:
    return alignment is not None and bool(Qt.AlignmentFlag(alignment) & Qt.AlignmentFlag.AlignRight)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Product": ["Rice", "Sugar"],
            "Revenue": [1500.5, 420.0],
            "Mixed": [1.0, "n/a"],
            "Count": [3, 4],  # int64: np.int64 cells, see test below
            "Amount": [Decimal("1.00"), Decimal("2.00")],
        }
    )


def test_float_column_header_right_aligns_text_column_keeps_default():
    model = PandasModel(_frame())
    assert _is_right(model.headerData(1, H, ALIGN))  # Revenue
    assert model.headerData(0, H, ALIGN) is None  # Product: Qt default
    assert model.headerData(2, H, ALIGN) is None  # Mixed: not every cell is numeric


def test_every_header_matches_its_cells():
    """A header right-aligns exactly when every cell below it does.

    Covers int64 (np.int64 cells) and Decimal columns too: whatever the
    cell rule decides for them, the header follows it.
    """
    model = PandasModel(_frame())
    for col in range(model.columnCount()):
        all_cells_right = all(_is_right(model.data(model.index(row, col), ALIGN)) for row in range(model.rowCount()))
        assert _is_right(model.headerData(col, H, ALIGN)) == all_cells_right, col


def test_set_data_recomputes_numeric_columns():
    model = PandasModel(pd.DataFrame({"Name": ["a"]}))
    assert model.headerData(0, H, ALIGN) is None

    model.set_data(pd.DataFrame({"Total": [9.5]}))

    assert _is_right(model.headerData(0, H, ALIGN))


def test_empty_frame_and_vertical_header():
    model = PandasModel(pd.DataFrame({"Total": pd.Series([], dtype=float)}))
    assert model.headerData(0, H, ALIGN) is None
    assert PandasModel(_frame()).headerData(0, Qt.Orientation.Vertical, ALIGN) is None
