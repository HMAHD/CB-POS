"""Tests for Issue #774: Roll out relative time formatting (format_relative_time) across key system views.

Verifies:
1. RelativeTimeTableWidgetItem displays friendly relative time with exact timestamp in tooltip.
2. Chronological sorting ordering is preserved (not alphabetical).
3. Trilingual support works across English, Sinhala, and Tamil.
4. Adoption across key dialogs and views (SaleHistoryDialog, BackupTabWidget, AdminToolsView, etc.).
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget

from cbpos.core.models import Product, Sale, User
from cbpos.core.services.maintenance_service import MaintenanceService
from cbpos.core.services.shift_service import ShiftService
from cbpos.i18n import set_language
from cbpos.ui.dialogs.sale_history_dialog import SaleHistoryDialog
from cbpos.ui.dialogs.shift_management_dialog import ShiftManagementDialog
from cbpos.ui.dialogs.stock_history_dialog import StockHistoryDialog
from cbpos.ui.views.admin_tools_view import AdminToolsView
from cbpos.ui.views.data_safety.backup_tab import BackupTabWidget
from cbpos.ui.views.purchase_view import PurchaseHistoryModel
from cbpos.ui.widgets.loading_overlay import LoadingOverlay
from cbpos.ui.widgets.table_helpers import RelativeTimeTableWidgetItem

pytestmark = pytest.mark.usefixtures("qapp")


class TestRelativeTimeTableWidgetItem:
    def test_displays_relative_time_and_sets_exact_tooltip(self):
        fixed_now = datetime(2026, 10, 16, 12, 0, 0)
        dt_5m = fixed_now - timedelta(minutes=5)

        item = RelativeTimeTableWidgetItem(dt_5m, fmt="%Y-%m-%d %H:%M", now=fixed_now)

        assert item.text() == "5 minutes ago"
        assert item.toolTip() == "2026-10-16 11:55"

    def test_handles_date_object_and_string(self):
        fixed_now = datetime(2026, 10, 16, 0, 0, 0)
        d = date(2026, 10, 14)
        item_date = RelativeTimeTableWidgetItem(d, fmt="%Y-%m-%d", now=fixed_now)
        assert item_date.text() == "2 days ago"
        assert item_date.toolTip() == "2026-10-14"

        item_str = RelativeTimeTableWidgetItem("2026-10-15 23:59:30", now=fixed_now)
        assert item_str.text() == "Just now"
        assert "2026-10-15 23:59" in item_str.toolTip()

    def test_handles_none_or_empty(self):
        item_none = RelativeTimeTableWidgetItem(None)
        assert item_none.text() == ""
        assert item_none.toolTip() == ""

        item_empty = RelativeTimeTableWidgetItem("")
        assert item_empty.text() == ""
        assert item_empty.toolTip() == ""

    def test_chronological_sorting_not_alphabetical(self):
        table = QTableWidget(3, 1)
        base = datetime(2026, 10, 16, 12, 0, 0)

        # Lexicographically: "1 day ago" < "2 hours ago" < "5 minutes ago"
        # Chronologically: 1 day ago < 2 hours ago < 5 minutes ago
        # But if alphabetical text sorting were used:
        # "1 day ago" < "2 hours ago" < "5 minutes ago"
        # Let's use 10 minutes ago vs 2 hours ago:
        # Lexicographically: "10 minutes ago" < "2 hours ago"
        # Chronologically: 2 hours ago < 10 minutes ago!
        dt_10m = base - timedelta(minutes=10)
        dt_2h = base - timedelta(hours=2)
        dt_1d = base - timedelta(days=1)

        item_10m = RelativeTimeTableWidgetItem(dt_10m, now=base)
        item_2h = RelativeTimeTableWidgetItem(dt_2h, now=base)
        item_1d = RelativeTimeTableWidgetItem(dt_1d, now=base)

        table.setItem(0, 0, item_10m)
        table.setItem(1, 0, item_2h)
        table.setItem(2, 0, item_1d)

        # In Python list sort
        items = [item_10m, item_2h, item_1d]
        items.sort()
        # Oldest first: 1 day ago, then 2 hours ago, then 10 minutes ago
        assert items[0].text() == "1 day ago"
        assert items[1].text() == "2 hours ago"
        assert items[2].text() == "10 minutes ago"

        # In QTableWidget sortItems
        table.sortItems(0, Qt.SortOrder.AscendingOrder)
        assert table.item(0, 0).text() == "1 day ago"
        assert table.item(1, 0).text() == "2 hours ago"
        assert table.item(2, 0).text() == "10 minutes ago"

    def test_trilingual_support(self):
        fixed_now = datetime(2026, 10, 16, 12, 0, 0)
        dt_just_now = fixed_now - timedelta(seconds=15)

        # English
        set_language("en")
        item_en = RelativeTimeTableWidgetItem(dt_just_now, now=fixed_now)
        assert item_en.text() == "Just now"

        # Sinhala
        set_language("si")
        item_si = RelativeTimeTableWidgetItem(dt_just_now, now=fixed_now)
        assert item_si.text() == "දැන්"

        # Tamil
        set_language("ta")
        item_ta = RelativeTimeTableWidgetItem(dt_just_now, now=fixed_now)
        assert item_ta.text() == "இப்போது"

        # Reset back to English
        set_language("en")


class TestViewIntegrations:
    def test_sale_history_dialog_relative_time(self, db_session):
        user = User(username="cashier1", pin_hash="hash")

        sale = Sale(
            document_number="INV-001",
            date=datetime.now() - timedelta(hours=2),
            total_amount=150.0,
            status="COMPLETED",
            payment_method="CASH",
            user=user,
        )

        db_session.add_all([user, sale])
        db_session.flush()

        dialog = SaleHistoryDialog()
        dialog._sales = [sale]
        dialog._populate_sales_table()

        # Check table cell
        date_item = dialog.sales_table.item(0, 1)
        assert "hour" in date_item.text().lower()
        assert date_item.toolTip() != ""

        # Check detail selection
        dialog._on_sale_selected(dialog.sales_table.item(0, 0), None)
        assert "hour" in dialog.lbl_info_date.text().lower()
        assert dialog.lbl_info_date.toolTip() != ""

    def test_backup_tab_last_backup_and_table_relative_time(self):
        overlay = LoadingOverlay(None)
        tab = BackupTabWidget(overlay)

        status = {"date": "2026-10-16 10:00:00", "restorable": True}
        tab._on_backup_status(status)

        assert tab.lbl_last_backup.toolTip() == "2026-10-16 10:00:00"
        assert tab.lbl_last_backup.property("class") == "credit"

        # Test table
        tab._backup_data = [
            {
                "path": "/fake/cbpos.bak",
                "filename": "cbpos_20261016_100000.bak",
                "date": "2026-10-16 10:00:00",
                "size": "50 KB",
                "type": "manual",
            }
        ]
        tab._fill_backup_table()
        table_date_item = tab.backup_table.item(0, tab.COL_DATE)
        assert table_date_item.toolTip() == "2026-10-16 10:00:00"
        assert table_date_item.text() != ""

    def test_admin_tools_db_modified_relative_time(self):
        view = AdminToolsView()
        with patch.object(
            MaintenanceService,
            "get_full_database_info",
            return_value={
                "path": "/db/test.db",
                "size": "2.5 MB",
                "last_modified": "2026-10-16 09:30:00",
                "sqlite_version": "3.45.0",
                "tables": [],
            },
        ):
            view._load_db_info()

            assert "2026-10-16 09:30:00" in view.lbl_db_modified.text()
            assert view.lbl_db_modified.toolTip() == "2026-10-16 09:30:00"

    def test_purchase_history_model_relative_time(self):
        purchase = MagicMock()
        purchase.document_number = "GRN-001"
        purchase.date = datetime.now() - timedelta(days=3)
        purchase.supplier = None
        purchase.reference_external = ""
        purchase.items = []
        purchase.total_cost = 500.0
        purchase.status = "RECEIVED"

        model = PurchaseHistoryModel(purchases=[purchase])
        idx = model.index(0, 1)

        display_val = model.data(idx, Qt.ItemDataRole.DisplayRole)
        tooltip_val = model.data(idx, Qt.ItemDataRole.ToolTipRole)

        assert "day" in display_val.lower()
        assert purchase.date.strftime("%Y-%m-%d %H:%M") == tooltip_val

    def test_shift_management_started_relative_time(self):
        shift_start = datetime.now() - timedelta(minutes=45)
        summary = {
            "shift_id": 1,
            "user_name": "Akash",
            "start_time": shift_start,
        }

        with patch.object(ShiftService, "get_shift_summary", return_value=summary):
            dialog = ShiftManagementDialog(shift_id=1, user_id=1)

            assert "minute" in dialog.lbl_started.text().lower()
            assert dialog.lbl_started.toolTip() == shift_start.strftime("%Y-%m-%d %H:%M")

    def test_stock_history_dialog_relative_time(self):
        product = Product(name_en="Test Item", barcode="BC1", price=10.0)
        product.id = 42

        mock_move = MagicMock()
        mock_move.timestamp = datetime.now() - timedelta(hours=1)
        mock_move.type = "SALE"
        mock_move.document = None
        mock_move.user = None
        mock_move.qty_change = -1.0
        mock_move.balance_after = 9.0

        with patch("cbpos.core.services.stock_service.StockService.get_history", return_value=[mock_move]):
            dialog = StockHistoryDialog(product)
            item = dialog.table.item(0, 0)
            assert "hour" in item.text().lower()
            assert item.toolTip() == mock_move.timestamp.strftime("%Y-%m-%d %H:%M")
