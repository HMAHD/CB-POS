"""Unit tests for shared spacing constants, bar standards, and report header layouts (#577)."""

import pytest
from PyQt6.QtWidgets import QApplication, QGridLayout

from cbpos.ui.constants import (
    BAR_GROUP_SPACING,
    BAR_ITEM_SPACING,
    BAR_MARGIN_H,
    BAR_MARGIN_V,
    SPACING_LG,
    SPACING_MD,
    SPACING_SM,
    SPACING_XL,
    SPACING_XS,
    SPACING_XXL,
)
from cbpos.ui.views.stock_take_view import StockCountReportDialog


@pytest.fixture(autouse=True)
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_spacing_scale_values():
    """Verify spacing constants adhere to 4px / 8px progressive scale."""
    assert SPACING_XS == 4
    assert SPACING_SM == 8
    assert SPACING_MD == 12
    assert SPACING_LG == 16
    assert SPACING_XL == 24
    assert SPACING_XXL == 32


def test_standard_bar_dimensions():
    """Verify standard toolbar, filter bar, and footer dimensions."""
    assert BAR_MARGIN_H == 16
    assert BAR_MARGIN_V == 10
    assert BAR_ITEM_SPACING == 8
    assert BAR_GROUP_SPACING == 16


def test_stock_count_report_dialog_header_grid(monkeypatch):
    """Verify StockCountReportDialog presents header as a 24px-spaced label/value grid."""
    from datetime import datetime
    from unittest.mock import MagicMock

    mock_sc = MagicMock()
    mock_sc.document_number = "SC-2026-001"
    mock_sc.status = "COMPLETED"
    mock_sc.date = datetime(2026, 10, 12, 14, 30)
    mock_sc.note = "Annual inventory audit"
    mock_sc.total_variance_value = 0
    mock_sc.items = []

    monkeypatch.setattr(
        "cbpos.ui.views.stock_take_view.StockCountService.get_stock_count",
        lambda _id: mock_sc,
    )

    dialog = StockCountReportDialog(stock_count_id=1)

    # Find the QGridLayout in the dialog's layout
    grid = None
    for i in range(dialog.layout().count()):
        item = dialog.layout().itemAt(i)
        if item.layout() and isinstance(item.layout(), QGridLayout):
            grid = item.layout()
            break

    assert grid is not None, "Header info grid not found in StockCountReportDialog"
    assert grid.horizontalSpacing() == SPACING_XL  # 24px gaps
    # Row 0 has 4 label keys, Row 1 has 4 values
    assert grid.count() >= 8
