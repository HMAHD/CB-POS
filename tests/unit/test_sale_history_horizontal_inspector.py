"""Unit tests for SaleHistoryDialog horizontal master-detail inspector layout."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter

from cbpos.ui.dialogs.sale_history_dialog import SaleHistoryDialog


def test_sale_history_dialog_horizontal_splitter(qtbot):
    """Verify dialog layout uses a horizontal splitter between table and inspector."""
    with patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]):
        dialog = SaleHistoryDialog()
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "splitter")
    assert isinstance(dialog.splitter, QSplitter)
    assert dialog.splitter.orientation() == Qt.Orientation.Horizontal
    assert dialog.splitter.count() == 2


def test_sale_history_no_visible_reprint_or_refund_buttons(qtbot):
    """Verify reprint and refund buttons are NOT visible in the inspector (handled by dedicated dialogs)."""
    with patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]):
        dialog = SaleHistoryDialog()
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "btn_reprint")
    assert dialog.btn_reprint.isHidden() is True

    assert hasattr(dialog, "btn_refund")
    assert dialog.btn_refund.isHidden() is True

    assert hasattr(dialog, "refund_panel")
    assert dialog.refund_panel.isHidden() is True


def test_sale_history_receipt_inspector_rendering(qtbot):
    """Verify selecting a sale populates the authentic thermal receipt preview."""
    with patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]):
        dialog = SaleHistoryDialog()
    qtbot.addWidget(dialog)

    # Initial state: prompt visible, preview hidden/empty
    assert dialog.lbl_select_prompt.isHidden() is False
    assert dialog.preview_scroll.isHidden() is True
    assert len(dialog.receipt_preview._commands) == 0

    mock_sale = MagicMock()
    mock_sale.id = 101
    mock_sale.document_number = "INV-2026-00041"
    mock_sale.date = datetime(2026, 10, 20, 10, 30, 0)
    mock_sale.total_amount = 1500.0
    mock_sale.net_revenue = 1500.0
    mock_sale.payment_method = "CASH"
    mock_sale.status = "COMPLETED"
    mock_sale.customer = None
    mock_sale.user = None
    mock_sale.items = []
    mock_sale.payments = []
    mock_sale.tax_vat = 0
    mock_sale.tax_sscl = 0
    mock_sale.loyalty_points_redeemed = 0
    mock_sale.loyalty_points_value = 0
    mock_sale.loyalty_points_earned = 0
    mock_sale.loyalty_points_balance = None
    mock_sale.additional_discount_type = "NONE"
    mock_sale.additional_discount_value = 0
    mock_sale.refund_of_sale_id = None

    # Populate table and select the sale row
    dialog._sales = [mock_sale]
    dialog._populate_sales_table()
    dialog.sales_table.setCurrentCell(0, 0)

    # After selection: prompt hidden, preview visible with commands
    assert dialog.lbl_select_prompt.isHidden() is True
    assert dialog.preview_scroll.isHidden() is False
    assert len(dialog.receipt_preview._commands) > 0

    # Deselection returns to prompt
    dialog.sales_table.clearSelection()
    dialog.sales_table.setCurrentItem(None)
    assert dialog.lbl_select_prompt.isHidden() is False
    assert dialog.preview_scroll.isHidden() is True
    assert len(dialog.receipt_preview._commands) == 0
