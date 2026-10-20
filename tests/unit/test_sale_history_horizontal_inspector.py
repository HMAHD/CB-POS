"""Unit tests for SaleHistoryDialog digital inspector and ReceiptReprintDialog thermal preview."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QSplitter

from cbpos.ui.dialogs.receipt_reprint_dialog import ReceiptReprintDialog
from cbpos.ui.dialogs.sale_history_dialog import SaleHistoryDialog


def _create_mock_sale():
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
    return mock_sale


def test_sale_history_dialog_horizontal_splitter(qtbot):
    """Verify dialog layout uses a horizontal splitter between table and inspector."""
    with patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]):
        dialog = SaleHistoryDialog()
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "splitter")
    assert isinstance(dialog.splitter, QSplitter)
    assert dialog.splitter.orientation() == Qt.Orientation.Horizontal
    assert dialog.splitter.count() == 2


def test_sale_history_digital_inspector_and_refund_action(qtbot):
    """Verify digital inspector card shows metadata, line items, and refund button."""
    with patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]):
        dialog = SaleHistoryDialog()
    qtbot.addWidget(dialog)

    # Initial state: prompt visible, inspector content hidden
    assert dialog.lbl_select_prompt.isHidden() is False
    assert dialog.inspector_content.isHidden() is True

    mock_sale = _create_mock_sale()
    dialog._sales = [mock_sale]
    dialog._populate_sales_table()
    dialog.sales_table.setCurrentCell(0, 0)

    # After selection: prompt hidden, inspector content visible
    assert dialog.lbl_select_prompt.isHidden() is True
    assert dialog.inspector_content.isHidden() is False
    assert "INV-2026-00041" in dialog.btn_copy_invoice.text()
    assert dialog.btn_refund.isEnabled() is True


def test_sale_history_copy_invoice_to_clipboard(qtbot):
    """Verify clicking the invoice badge or table cell copies invoice number to clipboard."""
    with patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]):
        dialog = SaleHistoryDialog()
    qtbot.addWidget(dialog)

    mock_sale = _create_mock_sale()
    dialog._sales = [mock_sale]
    dialog._populate_sales_table()
    dialog.sales_table.setCurrentCell(0, 0)

    # Click badge to copy
    dialog.btn_copy_invoice.click()
    assert QGuiApplication.clipboard().text() == "INV-2026-00041"

    # Click table cell column 0
    dialog._on_table_cell_clicked(0, 0)
    assert QGuiApplication.clipboard().text() == "INV-2026-00041"


def test_sale_history_refund_handover(qtbot):
    """Verify clicking refund opens RefundDialog pre-loaded with sale."""
    with patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]):
        dialog = SaleHistoryDialog()
    qtbot.addWidget(dialog)

    mock_sale = _create_mock_sale()
    dialog._sales = [mock_sale]
    dialog._populate_sales_table()
    dialog.sales_table.setCurrentCell(0, 0)

    with patch("cbpos.ui.dialogs.refund_dialog.RefundDialog.exec") as mock_exec:
        mock_exec.return_value = 0
        dialog.btn_refund.click()
        mock_exec.assert_called_once()


def test_receipt_reprint_dialog_thermal_preview(qtbot):
    """Verify ReceiptReprintDialog renders live thermal preview when a sale is selected."""
    dialog = ReceiptReprintDialog()
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "splitter")
    assert dialog.splitter.orientation() == Qt.Orientation.Horizontal
    assert dialog.lbl_preview_prompt.isHidden() is False
    assert dialog.preview_scroll.isHidden() is True

    mock_sale = _create_mock_sale()
    dialog.results = [mock_sale]
    dialog._populate_table()
    dialog.results_table.setCurrentCell(0, 1)

    assert dialog.lbl_preview_prompt.isHidden() is True
    assert dialog.preview_scroll.isHidden() is False
    assert len(dialog.receipt_preview._commands) > 0
    assert dialog.btn_reprint.isEnabled() is True


def test_receipt_reprint_quick_filters_and_search(qtbot):
    """Verify ReceiptReprintDialog has quick filter chips and searches across dates when term entered."""
    with patch("cbpos.ui.dialogs.receipt_reprint_dialog.SaleQueryService.get_sales_history") as mock_get:
        mock_get.return_value = []
        dialog = ReceiptReprintDialog()
        qtbot.addWidget(dialog)

        # Has filter chips
        assert "today" in dialog._filter_buttons
        assert "yesterday" in dialog._filter_buttons
        assert "this_week" in dialog._filter_buttons
        assert "this_month" in dialog._filter_buttons
        assert dialog._filter_buttons["today"].isChecked() is True

        # Click yesterday chip
        dialog._filter_buttons["yesterday"].click()
        assert dialog._active_filter == "yesterday"
        assert mock_get.call_count >= 2

        # Search term removes date bounds
        mock_get.reset_mock()
        dialog.search_input.setText("Saman")
        dialog.perform_search()
        mock_get.assert_called_with(
            from_date=None,
            to_date=None,
            search_term="Saman",
            limit=100,
        )


def test_side_menu_documents_removed(qtbot):
    """Verify POS SideMenu does not include documents tile in quick nav buttons."""
    from cbpos.ui.widgets.side_menu import SideMenu

    menu = SideMenu()
    qtbot.addWidget(menu)

    # documents tile is None and not in _nav_buttons
    assert menu.btn_documents is None
    assert hasattr(menu, "documents_clicked")
    for btn in menu._nav_buttons:
        assert getattr(btn, "_label_key", None) != "side_menu.documents"


def test_sale_summary_labels_transparent(qtbot):
    """Verify financial summary labels have transparent property to avoid patchy dark background."""
    with patch("cbpos.ui.dialogs.sale_history_dialog.SaleQueryService.get_sales_history", return_value=[]):
        dialog = SaleHistoryDialog()
    qtbot.addWidget(dialog)

    assert dialog.lbl_sum_subtotal_hdr.property("class") == "transparent"
    assert dialog.lbl_sum_subtotal_val.property("class") == "transparent"
    assert dialog.lbl_sum_discount_hdr.property("class") == "transparent"
    assert dialog.lbl_sum_discount_val.property("class") == "transparent"
    assert dialog.lbl_sum_tax_hdr.property("class") == "transparent"
    assert dialog.lbl_sum_tax_val.property("class") == "transparent"
    assert dialog.lbl_sum_total_hdr.property("class") == "bold"
